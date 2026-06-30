# Meto AI — Implementation Plan

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
>
> **Timeline tổng:** 6 tuần | **4 Phases**
>
> **Quy tắc merge:** Không merge bất kỳ PR nào khi chưa pass Codex review.

---

## Tổng quan timeline

```
Week 1-2:  Phase 1 — Foundation
Week 3-4:  Phase 2 — Context Integration
Week 5:    Phase 3 — UX Polish
Week 6:    Phase 4 — Safety & Launch
```

---

## Phase 1 — Foundation (2 tuần)

### Mục tiêu
Xây dựng khung cốt lõi: AI provider kết nối được, chat endpoint hoạt động, UI cơ bản render được. Chưa có context thực, chưa có animation.

---

### Backend Tasks

#### Task B1.1 — AIProvider Abstraction
**File:** `app/ai/providers/base.py`, `app/ai/providers/claude.py`, `app/ai/providers/openai.py`, `app/ai/providers/__init__.py`

```python
# base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class AIProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider availability."""
        ...

# claude.py — implement với Anthropic SDK
# openai.py — implement với OpenAI SDK
# __init__.py — factory: get_provider() → primary (Claude) hoặc fallback (OpenAI)
```

**Acceptance criteria:**
- [ ] `AIProvider` abstract class được định nghĩa
- [ ] `ClaudeProvider` implement đầy đủ với retry (3 lần, exponential backoff)
- [ ] `OpenAIProvider` implement đầy đủ
- [ ] Factory function `get_ai_provider()` tự động fallback khi Claude lỗi
- [ ] Unit tests cho cả 2 providers (mock API)
- [ ] Provider name không bao giờ lộ ra ngoài module này

#### Task B1.2 — Context Engine Skeleton
**File:** `app/ai/context_engine.py`

```python
class ContextEngine:
    def __init__(self, user_id: str, db: AsyncSession, redis: Redis):
        self.user_id = user_id
        self.db = db
        self.redis = redis

    async def assemble(
        self,
        screen_id: str,
        entity_id: str | None = None,
        consent: UserAIConsent | None = None,
    ) -> dict:
        """
        Phase 1: trả về mock data có cấu trúc đúng.
        Phase 2: wire đến real data.
        """
        ...
```

**Acceptance criteria:**
- [ ] `ContextEngine` class hoạt động với mock data
- [ ] 9 block schemas đều được định nghĩa (Pydantic models)
- [ ] Consent gating logic đã implement (skip blocks khi chưa consent)
- [ ] `context_isolation` test: gọi với `user_id` khác không trả về data

#### Task B1.3 — /ai/chat Endpoint
**File:** `app/routers/ai.py`

```python
@router.post("/ai/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    POST body: { message: string, screen_id: string, entity_id?: string }
    Returns: StreamingResponse (SSE format)
    """
    ...
```

**Acceptance criteria:**
- [ ] Endpoint yêu cầu JWT auth
- [ ] `user_id` lấy từ JWT, không từ request body
- [ ] Trả về SSE stream (Server-Sent Events)
- [ ] Timeout 30 giây
- [ ] Rate limit 30 req/min per user
- [ ] Fallback hoạt động: nếu Claude lỗi → OpenAI, không báo lỗi cho user

#### Task B1.4 — Audit Logging
**File:** `app/ai/audit.py`, migration `alembic/versions/xxx_create_meto_audit_logs.py`

**Acceptance criteria:**
- [ ] Table `meto_audit_logs` được tạo (schema theo 04_SAFETY_PRIVACY.md)
- [ ] Mỗi request ghi 1 audit entry
- [ ] Không log nội dung message/response
- [ ] Log ghi được: provider_used, fallback_used, context_blocks_used, response_time_ms

#### Task B1.5 — Safety Guardrails (Backend)
**File:** `app/ai/safety.py`

**Acceptance criteria:**
- [ ] `check_red_flags()` detect đúng 100% các phrase trong RED_FLAGS_EMERGENCY
- [ ] `should_override_with_escalation()` bypass AI call khi có emergency flag
- [ ] Escalation response template render đúng với `preferred_address`
- [ ] Unit tests: 20 test cases (10 positive, 10 negative)

---

### Frontend Tasks

#### Task F1.1 — MetoAura Component (Static)
**File:** `components/meto/MetoAura.tsx`

```typescript
type AuraState = "idle" | "listening" | "thinking" | "answering" | "completed";

interface MetoAuraProps {
  state: AuraState;
  size?: number;  // default 56
  className?: string;
}

export const MetoAura = ({ state, size = 56, className }: MetoAuraProps) => {
  // Phase 1: static render, no animation yet
  // Phase 3: add Framer Motion animations
  ...
};
```

**Acceptance criteria:**
- [ ] Component render đúng với 5 states (visual differences)
- [ ] Không crash với bất kỳ prop nào
- [ ] Storybook story (nếu có) hoặc test page

#### Task F1.2 — FloatingMetoButton
**File:** `components/meto/FloatingMetoButton.tsx`

**Acceptance criteria:**
- [ ] Render đúng vị trí (fixed, bottom-right)
- [ ] Tap mở ChatSheet
- [ ] Không overlap bottom navigation bar
- [ ] Touch target ≥ 44 × 44px
- [ ] Label "Hỏi Meto" hiển thị bên dưới

#### Task F1.3 — ChatSheet Component
**File:** `components/meto/ChatSheet.tsx`

**Acceptance criteria:**
- [ ] Bottom sheet slide up animation khi mở
- [ ] Dismiss khi drag down hoặc tap backdrop
- [ ] Hiển thị Meto Aura ở header
- [ ] Chat input hoạt động (type + send)
- [ ] Kết nối với `/ai/chat` endpoint
- [ ] Hiển thị streaming response (tokens hiện dần)
- [ ] Disclaimer banner hiển thị lần đầu

#### Task F1.4 — MetoContext
**File:** `contexts/MetoContext.tsx`

**Acceptance criteria:**
- [ ] Quản lý state: `isOpen`, `messages`, `isLoading`, `auraState`
- [ ] Expose `openChat(screenId, entityId?)` function
- [ ] Expose `sendMessage(text)` function
- [ ] Wrap vào AppLayout

---

### CI/Testing

**Acceptance criteria:**
- [ ] `pytest app/ai/` tất cả pass
- [ ] `jest components/meto/` tất cả pass
- [ ] Lint (ruff + eslint) không warning
- [ ] Codex review PR trước khi merge

---

## Phase 2 — Context Integration (2 tuần)

### Mục tiêu
Wire context engine đến real database. Meto bắt đầu biết thông tin thực của user. Quick prompts đúng theo màn. Chat history hoạt động.

---

### Backend Tasks

#### Task B2.1 — Wire 9 Context Blocks đến Real Data

**Files cần sửa:** `app/ai/context_engine.py` + 9 service functions

```
app/ai/context/
├── user_profile.py      # Block 1: query users + user_profiles
├── health_summary.py    # Block 2: query health_profiles, diagnoses
├── care_plan.py         # Block 3: query care_plans, care_tasks
├── medications.py       # Block 4: query prescriptions, medications
├── recent_labs.py       # Block 5: query lab_results (30 ngày gần nhất)
├── recent_metrics.py    # Block 6: query health_metrics (7 ngày gần nhất)
├── screen_context.py    # Block 7: built from request params
├── today_context.py     # Block 8: query tasks + appointments today
└── safety_flags.py      # Block 9: rules engine trên metrics + labs
```

**Acceptance criteria:**
- [ ] Mỗi block query đúng data của user đang đăng nhập
- [ ] Parameterized queries (không SQL injection)
- [ ] Cache Redis theo TTL đã spec
- [ ] Missing data xử lý gracefully (không crash)
- [ ] Integration test: context cho user A không chứa data của user B

#### Task B2.2 — Prompt Assembly Hoàn chỉnh
**File:** `app/ai/prompt_builder.py`

**Acceptance criteria:**
- [ ] System prompt (v1.0) inject đúng
- [ ] Developer prompt cá nhân hóa theo `preferred_address`
- [ ] Context blocks format đúng (JSON labeled)
- [ ] Token count ước tính trước khi gọi AI (warn nếu > 8000 input tokens)
- [ ] `prompt_version` được log vào audit

#### Task B2.3 — Redis Cache Layer
**File:** `app/ai/cache.py`

**Acceptance criteria:**
- [ ] Cache miss: fetch từ DB, lưu vào Redis
- [ ] Cache hit: return từ Redis, không query DB
- [ ] Cache invalidation khi user cập nhật data liên quan
- [ ] Cache key format: `meto:ctx:{user_id}:{block_name}`
- [ ] TTL đúng theo spec

#### Task B2.4 — Chat History Backend
**File:** `app/routers/ai.py`, migration

```python
# Table: meto_chat_sessions + meto_chat_messages
@router.get("/ai/chat/history")
async def get_chat_history(...): ...

@router.delete("/ai/chat/history")
async def clear_chat_history(...): ...
```

**Acceptance criteria:**
- [ ] Lưu messages (content) theo user
- [ ] GET history trả về 50 messages gần nhất
- [ ] DELETE xóa hoàn toàn (không soft delete)
- [ ] Tự động xóa messages > 90 ngày (cron job)

---

### Frontend Tasks

#### Task F2.1 — Screen Context Injection

Mỗi màn hình cần inject `screen_id` và `entity_id` khi mở Meto:

```typescript
// Trong DashboardScreen.tsx
const { openChat } = useMeto();
<FloatingMetoButton onClick={() => openChat("dashboard")} />

// Trong LabsScreen.tsx — khi xem 1 kết quả
<button onClick={() => openChat("labs", labResult.id)}>
  Hỏi Meto về kết quả này
</button>
```

**Files cần sửa:** Tất cả 7 màn hình chính.

**Acceptance criteria:**
- [ ] Mỗi màn hình inject đúng `screen_id`
- [ ] Inline "Hỏi Meto" buttons trên Labs và Medications
- [ ] `entity_id` được truyền khi xem item cụ thể

#### Task F2.2 — Quick Prompts per Screen
**File:** `components/meto/QuickPromptChips.tsx`, `lib/meto/quick-prompts.ts`

```typescript
export const QUICK_PROMPTS: Record<ScreenId, string[]> = {
  dashboard: ["Hôm nay tôi cần chú ý gì?", "Tóm tắt sức khỏe tuần này", ...],
  labs: ["Giải thích kết quả này", "Chỉ số nào cần theo dõi?", ...],
  // ...
};
```

**Acceptance criteria:**
- [ ] Quick prompts đúng theo spec (01_PRODUCT_SPEC.md)
- [ ] Tap quick prompt → tự điền vào input → auto send
- [ ] Horizontal scroll, không wrap

#### Task F2.3 — Chat History UI
**File:** `components/meto/ChatSheet.tsx` (update)

**Acceptance criteria:**
- [ ] Load 50 messages gần nhất khi mở ChatSheet
- [ ] Scroll to bottom tự động khi có message mới
- [ ] Hiển thị timestamp mỗi message
- [ ] "Xóa lịch sử" button trong menu

#### Task F2.4 — Consent Flow UI
**File:** `components/meto/ConsentModal.tsx`

**Acceptance criteria:**
- [ ] Modal hiện khi chưa có consent record
- [ ] Hiển thị rõ ràng dữ liệu nào được truy cập
- [ ] Link đến Privacy Policy
- [ ] "Chỉ dùng tính năng cơ bản" flow hoạt động
- [ ] Lưu consent khi đồng ý

---

## Phase 3 — UX Polish (1 tuần)

### Mục tiêu
Biến UI cơ bản thành trải nghiệm mượt mà, đẹp, đáng nhớ. Animation, memory, accessibility.

---

#### Task F3.1 — Meto Aura Animations (Framer Motion)
**File:** `components/meto/MetoAura.tsx` (update)

Implement đầy đủ 5 states theo spec trong 05_UI_UX_SPEC.md.

**Acceptance criteria:**
- [ ] Idle animation: breath loop 3s
- [ ] Listening: glow tăng + ripple nhẹ
- [ ] Thinking: 3 ripple đồng tâm, staggered 0.4s
- [ ] Answering: glow pulse 1.5s loop
- [ ] Completed: burst + heart, play once
- [ ] State transitions smooth (không giật)
- [ ] `prefers-reduced-motion`: tắt animation khi user bật reduced motion

#### Task F3.2 — Memory Opt-in Flow
**File:** `components/meto/MemoryOptInSheet.tsx`, `app/ai/memory.py`

**Acceptance criteria:**
- [ ] Trigger sau 3 lần dùng Meto thành công
- [ ] Thu thập: cách xưng hô, mục tiêu, phong cách
- [ ] Lưu vào backend `user_meto_memory` table
- [ ] User có thể xem/xóa trong Settings
- [ ] Context engine inject memory vào developer prompt

#### Task F3.3 — Accessibility Pass

**Acceptance criteria:**
- [ ] Tất cả interactive elements có `aria-label`
- [ ] Chat dialog có `role="dialog"` + `aria-modal="true"`
- [ ] Messages có `aria-live="polite"`
- [ ] Tab order logic
- [ ] VoiceOver / TalkBack test trên iOS + Android

#### Task F3.4 — Typography & Spacing Polish

**Acceptance criteria:**
- [ ] Font size: messages 15px, labels 13px, disclaimers 12px
- [ ] Line height: 1.5 cho user bubble, 1.6 cho Meto bubble
- [ ] Paragraph spacing trong Meto response (markdown render)
- [ ] Emoji render đúng cross-platform

---

## Phase 4 — Safety & Launch (1 tuần)

### Mục tiêu
Kiểm tra toàn diện safety, context isolation, và deploy lên staging.

---

#### Task B4.1 — Safety Guardrail Testing
Chạy đầy đủ test suite từ 07_ACCEPTANCE_TESTS.md, section Safety Tests.

**Acceptance criteria:**
- [ ] 100% RED_FLAGS_EMERGENCY detected và escalated
- [ ] Không có response nào chứa forbidden phrases
- [ ] Escalation response render đúng với preferred_address
- [ ] Fallback scenario: khi Claude down, OpenAI response vẫn safe

#### Task B4.2 — Context Isolation Testing
**Acceptance criteria:**
- [ ] Test với 10 user pairs: user A không thấy data user B
- [ ] SQL injection attempts bị block
- [ ] JWT manipulation bị từ chối (401)
- [ ] RLS policy hoạt động đúng

#### Task B4.3 — Audit Log Review
**Acceptance criteria:**
- [ ] Mọi request đều có audit entry
- [ ] Không có PII (tên, địa chỉ) trong audit log
- [ ] Không có health data trong audit log
- [ ] `provider_used` + `fallback_used` ghi đúng

#### Task F4.1 — UAT Checklist

**Acceptance criteria:**
- [ ] 5 tester thực tế dùng thử trên iPhone (iOS 16+) và Android
- [ ] Meto trả lời được tất cả quick prompts
- [ ] Consent flow hoàn chỉnh
- [ ] Không có crash trong 1 giờ sử dụng liên tục
- [ ] Response time < 3 giây (P95)

#### Task D4.1 — Staging Deploy

**File:** `.github/workflows/deploy-staging.yml` (update), Azure Container Apps config

**Acceptance criteria:**
- [ ] Build pass CI
- [ ] Codex review PASSED
- [ ] Deploy lên staging environment
- [ ] Smoke test: gọi `/ai/chat` từ staging UI → response nhận được
- [ ] Audit log ghi vào staging DB

---

## Quy tắc & Conventions

### Không merge nếu:
1. Codex review chưa approve
2. CI tests chưa pass (0 failure)
3. Còn TODO/FIXME liên quan đến safety hoặc privacy
4. Có hardcoded user_id hoặc provider name trong code

### File naming conventions
```
Backend:
  app/ai/providers/{name}.py
  app/ai/context/{block_name}.py
  app/ai/safety.py
  app/ai/audit.py
  app/ai/memory.py
  app/routers/ai.py

Frontend:
  components/meto/{ComponentName}.tsx
  contexts/MetoContext.tsx
  lib/meto/{util}.ts
  hooks/useMeto.ts
```

### Environment variables cần thêm
```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
REDIS_URL=...
METO_PROMPT_VERSION=v1.0
METO_RATE_LIMIT_PER_MINUTE=30
METO_MAX_TOKENS_INPUT=8000
METO_MAX_TOKENS_OUTPUT=2000
```

---

*Xem thêm: 07_ACCEPTANCE_TESTS.md (test cases chi tiết)*
