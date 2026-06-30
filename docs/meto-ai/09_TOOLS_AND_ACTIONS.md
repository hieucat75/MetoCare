# Meto AI — Tools & Actions Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Tool Engine là hệ thống cho phép Meto thực hiện **hành động thực tế** trong ứng dụng MetoCare thay vì chỉ trả lời text. Khi user hỏi "Tạo nhắc nhở uống thuốc" hoặc "Ghi lại huyết áp vừa đo", Meto không chỉ hướng dẫn — Meto thực hiện luôn.

**Nguyên tắc thiết kế:**
- Tools là **opt-in per action** — mỗi lần gọi tool cần user confirmation
- Audit log cho mọi tool execution
- Rate limit để tránh abuse
- Thiết kế tương thích với MCP (Model Context Protocol) để mở rộng sau

**File backend:**
- `app/ai/tool_engine.py` — Registry, dispatch, execution
- `app/ai/tools/` — Từng tool implementation
- `app/ai/tool_security.py` — Permission model, rate limiting
- `app/models/tool_audit.py` — Audit schema

---

## 1. Tool Engine Architecture

### 1.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        TOOL ENGINE                              │
│                                                                 │
│  ┌──────────────┐    ┌─────────────────┐   ┌───────────────┐  │
│  │   Registry   │    │    Dispatcher   │   │    Executor   │  │
│  │              │    │                 │   │               │  │
│  │ register()   │    │ select_tool()   │   │ execute()     │  │
│  │ discover()   │────▶ build_args()   │───▶ validate()    │  │
│  │ get_schema() │    │ check_consent() │   │ call()        │  │
│  └──────────────┘    └─────────────────┘   │ audit_log()  │  │
│                                            └───────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    TOOL REGISTRY                          │  │
│  │                                                           │  │
│  │  explain_lab  │  explain_medication  │  create_reminder  │  │
│  │  schedule_appointment  │  navigate_screen                │  │
│  │  update_care_plan  │  record_metric  │                   │  │
│  │  generate_health_summary  │  nutrition_recommendation    │  │
│  │  exercise_recommendation  │  symptom_intake              │  │
│  │  prepare_doctor_questions                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Tool Registration

```python
# app/ai/tool_engine.py

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

@dataclass
class ToolDefinition:
    name: str                           # snake_case, globally unique
    display_name: str                   # "Tạo nhắc nhở"
    description: str                    # Mô tả cho AI model
    version: str                        # "1.0.0" — semantic versioning
    
    # Permission model
    requires_consent: bool              # User phải confirm trước khi execute
    permission_scope: list[str]         # ["medications:read", "reminders:write"]
    
    # Rate limiting
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 20
    
    # Schema (OpenAI function calling format)
    parameters_schema: dict             # JSON Schema
    
    # Execution
    handler: Callable[..., Awaitable[ToolResult]]
    
    # Conditions khi nào tool available
    available_on_screens: list[str]     # Empty = all screens
    requires_context_blocks: list[str]  # Context blocks phải có để dùng tool
    
    # MCP metadata (cho future compatibility)
    mcp_namespace: str = "meto"
    is_mcp_compatible: bool = True

class ToolRegistry:
    _tools: dict[str, ToolDefinition] = {}
    
    @classmethod
    def register(cls, tool: ToolDefinition):
        cls._tools[tool.name] = tool
    
    @classmethod  
    def get_schemas_for_request(
        cls, 
        screen_id: str,
        available_context_blocks: list[str]
    ) -> list[dict]:
        """Return tool schemas phù hợp với screen và context hiện tại"""
        schemas = []
        for tool in cls._tools.values():
            if tool.available_on_screens and screen_id not in tool.available_on_screens:
                continue
            if not all(b in available_context_blocks for b in tool.requires_context_blocks):
                continue
            schemas.append(tool.to_openai_schema())
        return schemas
```

### 1.3 Tool Call Flow

```
User Message
    │
    ▼
┌─────────────────────────────────────────────┐
│              INTENT DETECTION               │
│                                             │
│  AI model phân tích message + context       │
│  → Quyết định có gọi tool không            │
│  → Nếu có: chọn tool + extract arguments   │
└─────────────────────────────────────────────┘
    │ tool_call detected in AI response
    ▼
┌─────────────────────────────────────────────┐
│           PERMISSION CHECK                  │
│                                             │
│  1. Tool có trong registry không?           │
│  2. User có consent scope cần thiết?        │
│  3. Rate limit chưa bị exceed?             │
│  4. Arguments hợp lệ theo schema?          │
└─────────────────────────────────────────────┘
    │ pass
    ▼
┌─────────────────────────────────────────────┐
│         USER CONFIRMATION (nếu cần)         │
│                                             │
│  Meto hiển thị preview action + Ask:        │
│  "Meto sẽ [action]. Anh/chị đồng ý không?" │
│  [Đồng ý] [Không cần]                      │
└─────────────────────────────────────────────┘
    │ confirmed
    ▼
┌─────────────────────────────────────────────┐
│              TOOL EXECUTION                 │
│                                             │
│  1. Execute tool handler                    │
│  2. Ghi audit log                          │
│  3. Return ToolResult                       │
└─────────────────────────────────────────────┘
    │ result
    ▼
┌─────────────────────────────────────────────┐
│          RESULT INJECTION                   │
│                                             │
│  Inject tool result vào next message:       │
│  role="tool", content=result.to_prompt()    │
│  AI generates final response to user        │
└─────────────────────────────────────────────┘
    │
    ▼
Meto Response (streaming)
```

### 1.4 Tool Result Injection

```python
@dataclass
class ToolResult:
    tool_name: str
    tool_call_id: str
    success: bool
    
    # For success
    data: dict | None = None
    summary_for_prompt: str = ""   # Human-readable summary AI dùng để generate response
    
    # For error
    error_code: str | None = None
    error_message: str | None = None
    user_facing_error: str | None = None  # Localized, friendly

def to_prompt_message(self) -> dict:
    """Format để inject vào conversation history"""
    if self.success:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": f"[Tool: {self.tool_name}] Thành công. {self.summary_for_prompt}"
        }
    else:
        return {
            "role": "tool", 
            "tool_call_id": self.tool_call_id,
            "content": f"[Tool: {self.tool_name}] Lỗi: {self.error_message}. {self.user_facing_error}"
        }
```

---

## 2. Tool Security Model

### 2.1 Permission Scopes

```python
PERMISSION_SCOPES = {
    # Read-only scopes
    "labs:read":           "Xem kết quả xét nghiệm",
    "medications:read":    "Xem danh sách thuốc",
    "metrics:read":        "Xem chỉ số sức khỏe",
    "care_plan:read":      "Xem kế hoạch chăm sóc",
    "profile:read":        "Xem hồ sơ sức khỏe",
    
    # Write scopes — cần explicit consent
    "reminders:write":     "Tạo và quản lý nhắc nhở",
    "appointments:write":  "Tạo lịch hẹn",
    "metrics:write":       "Ghi nhận chỉ số sức khỏe",
    "care_plan:write":     "Cập nhật kế hoạch chăm sóc",
    "navigation:execute":  "Điều hướng màn hình",
    
    # Sensitive scopes — cần separate consent
    "health_summary:generate": "Tạo tóm tắt sức khỏe",
    "symptom:collect":         "Thu thập thông tin triệu chứng",
}
```

### 2.2 Consent Requirements

```python
# Tools yêu cầu explicit confirmation mỗi lần:
REQUIRES_PER_ACTION_CONSENT = [
    "create_reminder",        # Tạo data mới
    "schedule_appointment",   # Tạo data mới
    "record_metric",          # Write to health data
    "update_care_plan",       # Write to care plan
    "symptom_intake",         # Collect sensitive data
]

# Tools chỉ cần consent ban đầu (one-time):
REQUIRES_INITIAL_CONSENT = [
    "explain_lab",
    "explain_medication",
    "navigate_screen",
    "generate_health_summary",
    "nutrition_recommendation",
    "exercise_recommendation",
    "prepare_doctor_questions",
]
```

### 2.3 Rate Limiting

```python
TOOL_RATE_LIMITS = {
    "explain_lab":              {"per_minute": 10, "per_hour": 50},
    "explain_medication":       {"per_minute": 10, "per_hour": 50},
    "create_reminder":          {"per_minute": 5,  "per_hour": 20},
    "schedule_appointment":     {"per_minute": 3,  "per_hour": 10},
    "navigate_screen":          {"per_minute": 20, "per_hour": 100},
    "update_care_plan":         {"per_minute": 5,  "per_hour": 20},
    "record_metric":            {"per_minute": 10, "per_hour": 40},
    "generate_health_summary":  {"per_minute": 2,  "per_hour": 5},
    "nutrition_recommendation": {"per_minute": 5,  "per_hour": 20},
    "exercise_recommendation":  {"per_minute": 5,  "per_hour": 20},
    "symptom_intake":           {"per_minute": 2,  "per_hour": 5},
    "prepare_doctor_questions": {"per_minute": 3,  "per_hour": 10},
}
```

### 2.4 Audit Log

```sql
CREATE TABLE tool_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    session_id      TEXT NOT NULL,
    conversation_id UUID NOT NULL,
    
    tool_name       TEXT NOT NULL,
    tool_call_id    TEXT NOT NULL,
    
    -- Execution
    status          TEXT NOT NULL,   -- 'success' | 'failed' | 'cancelled_by_user' | 'rate_limited'
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER,
    
    -- Arguments (anonymized — no raw health values)
    tool_inputs_summary TEXT,       -- "reminder for Metformin at 12:00"
    tool_result_summary TEXT,       -- "reminder_id: xyz123 created"
    
    -- Error info
    error_code      TEXT,
    
    -- Security
    permission_scope TEXT[],
    consent_verified BOOLEAN NOT NULL,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tool_audit_user ON tool_audit_logs(user_id, created_at);
CREATE INDEX idx_tool_audit_tool ON tool_audit_logs(tool_name, created_at);
```

---

## 3. Tool Definitions

---

### Tool 01: `explain_lab`

**Purpose:** Giải thích kết quả xét nghiệm đang được xem trên màn hình Labs, sử dụng context của lab result cụ thể đó.

```python
ToolDefinition(
    name="explain_lab",
    display_name="Giải thích kết quả xét nghiệm",
    description=(
        "Giải thích chi tiết một kết quả xét nghiệm cụ thể: "
        "ý nghĩa của chỉ số, ngưỡng tham chiếu, xu hướng so với lần trước, "
        "và việc nên làm. KHÔNG chẩn đoán bệnh."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["labs:read"],
    rate_limit_per_minute=10,
    available_on_screens=["labs"],
    requires_context_blocks=["recent_labs", "health_summary"],
    parameters_schema={
        "type": "object",
        "properties": {
            "lab_id": {
                "type": "string",
                "description": "UUID của lab result cần giải thích"
            },
            "test_name": {
                "type": "string",
                "description": "Tên xét nghiệm (vd: HbA1c, Glucose, Creatinine)"
            },
            "focus_aspect": {
                "type": "string",
                "enum": ["value_meaning", "trend", "what_to_do", "full_explanation"],
                "description": "User muốn tập trung vào khía cạnh nào"
            }
        },
        "required": ["test_name"]
    }
)
```

**Handler Logic:**
```python
async def explain_lab_handler(
    user_id: str,
    lab_id: str | None,
    test_name: str,
    focus_aspect: str = "full_explanation",
    context: dict
) -> ToolResult:
    
    # Load lab data từ context (đã được assembled)
    lab_data = find_lab_in_context(context["recent_labs"], lab_id, test_name)
    
    if not lab_data:
        return ToolResult(
            success=False,
            error_code="lab_not_found",
            user_facing_error=f"Không tìm thấy kết quả xét nghiệm '{test_name}' trong hồ sơ."
        )
    
    # Find historical trend
    historical = await get_lab_history(user_id, test_name, limit=5)
    
    # Build rich context for explanation
    explanation_context = {
        "current": lab_data,
        "history": historical,
        "patient_conditions": context["health_summary"]["primary_conditions"],
        "focus": focus_aspect
    }
    
    return ToolResult(
        success=True,
        data=explanation_context,
        summary_for_prompt=(
            f"Kết quả {test_name}: {lab_data['value']} {lab_data['unit']} "
            f"(ngưỡng: {lab_data['reference_range']}, status: {lab_data['status']}). "
            f"Trend 5 lần gần nhất: {format_trend(historical)}. "
            f"Focus: {focus_aspect}."
        )
    )
```

**UX Flow:**
1. User ở Labs screen, nhìn thấy HbA1c 7.8%
2. User hỏi: "Kết quả này có ý nghĩa gì?"
3. Meto detect context = labs screen, entity = HbA1c
4. Gọi `explain_lab` với test_name="HbA1c"
5. Tool load data + trend history
6. Meto generate explanation có cấu trúc với trend info

**Security:**
- Chỉ truy cập lab data của user đang auth
- Không cho phép gọi lab_id của user khác
- Rate limit: 10/phút

**Error Handling:**
| Lỗi | User message |
|-----|-------------|
| Lab not found | "Không tìm thấy kết quả xét nghiệm này trong hồ sơ của anh/chị." |
| No consent | "Anh/chị chưa cho phép Meto xem kết quả xét nghiệm." |
| Stale data | "Kết quả này đã cũ (>30 ngày). Meto giải thích dựa trên kết quả gần nhất." |

---

### Tool 02: `explain_medication`

**Purpose:** Giải thích thông tin về thuốc đang được xem — công dụng, cách dùng, tác dụng phụ phổ biến. **KHÔNG prescribing.**

```python
ToolDefinition(
    name="explain_medication",
    display_name="Giải thích thông tin thuốc",
    description=(
        "Giải thích thông tin về thuốc đang được xem: công dụng, "
        "cơ chế hoạt động, tác dụng phụ phổ biến, lưu ý khi dùng. "
        "KHÔNG thêm thuốc mới, KHÔNG thay đổi liều, KHÔNG khuyên dừng thuốc."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["medications:read"],
    rate_limit_per_minute=10,
    available_on_screens=["medications"],
    requires_context_blocks=["active_medications"],
    parameters_schema={
        "type": "object",
        "properties": {
            "medication_name": {
                "type": "string",
                "description": "Tên thuốc cần giải thích"
            },
            "generic_name": {
                "type": "string",
                "description": "Tên hoạt chất (nếu có)"
            },
            "focus_aspect": {
                "type": "string",
                "enum": ["purpose", "side_effects", "how_to_take", "interactions", "full"],
                "description": "Khía cạnh cần giải thích"
            }
        },
        "required": ["medication_name"]
    }
)
```

**Handler Logic:**
- Load medication from context (active_medications block)
- Query internal drug database cho reference info
- Personalize với patient conditions (vd: Metformin + đái tháo đường)
- Highlight adherence info nếu có trong context

**Security:**
- Chỉ giải thích thuốc trong danh sách của user — không lookup thuốc random
- Rõ ràng: "Đây là thông tin tham khảo, không thay đổi liều theo Meto"

**Error Handling:**
| Lỗi | User message |
|-----|-------------|
| Med not in list | "Meto không thấy thuốc này trong danh sách của anh/chị. Có thể kiểm tra lại tên thuốc?" |
| Drug DB error | "Meto đang tra cứu thông tin. Vui lòng thử lại sau." |

---

### Tool 03: `create_reminder`

**Purpose:** Tạo nhắc nhở uống thuốc hoặc đo chỉ số sức khỏe từ cuộc trò chuyện.

```python
ToolDefinition(
    name="create_reminder",
    display_name="Tạo nhắc nhở",
    description=(
        "Tạo nhắc nhở uống thuốc hoặc đo chỉ số sức khỏe. "
        "Dùng khi user nói muốn được nhắc, hoặc đặt lịch đo."
    ),
    version="1.0.0",
    requires_consent=True,   # Per-action confirmation required
    permission_scope=["reminders:write", "medications:read"],
    rate_limit_per_minute=5,
    available_on_screens=[],  # All screens
    requires_context_blocks=["active_medications"],
    parameters_schema={
        "type": "object",
        "properties": {
            "reminder_type": {
                "type": "string",
                "enum": ["medication", "metric_measurement", "appointment", "custom"],
                "description": "Loại nhắc nhở"
            },
            "title": {
                "type": "string",
                "description": "Tiêu đề nhắc nhở"
            },
            "medication_name": {
                "type": "string",
                "description": "Tên thuốc (nếu type=medication)"
            },
            "metric_type": {
                "type": "string", 
                "description": "Loại chỉ số (nếu type=metric_measurement)"
            },
            "scheduled_time": {
                "type": "string",
                "format": "time",
                "description": "Giờ nhắc nhở (HH:MM, 24h)"
            },
            "frequency": {
                "type": "string",
                "enum": ["daily", "weekly", "custom"],
                "description": "Tần suất"
            },
            "days_of_week": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 6},
                "description": "Ngày trong tuần (0=Mon, 6=Sun) nếu frequency=weekly"
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú thêm cho nhắc nhở"
            }
        },
        "required": ["reminder_type", "title", "scheduled_time", "frequency"]
    }
)
```

**Confirmation Preview:**
```
Meto sẽ tạo nhắc nhở:
━━━━━━━━━━━━━━━━━━━━━
📋 Uống Metformin 500mg
🕐 12:00 hàng ngày
━━━━━━━━━━━━━━━━━━━━━
[✓ Tạo nhắc nhở] [Hủy]
```

**Handler Logic:**
```python
async def create_reminder_handler(
    user_id: str,
    reminder_type: str,
    title: str,
    scheduled_time: str,
    frequency: str,
    medication_name: str | None = None,
    metric_type: str | None = None,
    days_of_week: list[int] | None = None,
    notes: str | None = None,
    context: dict = {}
) -> ToolResult:
    
    # Validate medication exists in user's list (if medication reminder)
    if reminder_type == "medication" and medication_name:
        meds = context.get("active_medications", {}).get("medications", [])
        med_names = [m["name"].lower() for m in meds]
        if medication_name.lower() not in med_names:
            return ToolResult(
                success=False,
                error_code="medication_not_in_list",
                user_facing_error=f"Không tìm thấy {medication_name} trong danh sách thuốc của anh/chị."
            )
    
    # Create reminder via reminder service
    reminder = await reminder_service.create({
        "user_id": user_id,
        "type": reminder_type,
        "title": title,
        "scheduled_time": scheduled_time,
        "frequency": frequency,
        "days_of_week": days_of_week,
        "notes": notes,
        "source": "meto_ai",
        "medication_name": medication_name,
        "metric_type": metric_type,
    })
    
    return ToolResult(
        success=True,
        data={"reminder_id": reminder.id, "next_trigger": reminder.next_trigger},
        summary_for_prompt=(
            f"Đã tạo nhắc nhở '{title}' lúc {scheduled_time} {frequency}. "
            f"ID: {reminder.id}. Nhắc nhở tiếp theo: {reminder.next_trigger}."
        )
    )
```

---

### Tool 04: `schedule_appointment`

**Purpose:** Gợi ý hoặc tạo lịch hẹn khám bác sĩ từ cuộc trò chuyện.

```python
ToolDefinition(
    name="schedule_appointment",
    display_name="Đặt lịch hẹn bác sĩ",
    description=(
        "Tạo lịch hẹn với bác sĩ hoặc cơ sở y tế. "
        "Dùng khi user muốn đặt lịch hoặc khi Meto gợi ý nên gặp bác sĩ."
    ),
    version="1.0.0",
    requires_consent=True,
    permission_scope=["appointments:write"],
    rate_limit_per_minute=3,
    available_on_screens=[],
    requires_context_blocks=["user_profile_summary"],
    parameters_schema={
        "type": "object",
        "properties": {
            "appointment_type": {
                "type": "string",
                "enum": ["regular_checkup", "follow_up", "specialist", "urgent", "lab_result_review"],
                "description": "Loại lịch hẹn"
            },
            "suggested_date": {
                "type": "string",
                "format": "date",
                "description": "Ngày gợi ý (YYYY-MM-DD)"
            },
            "suggested_time": {
                "type": "string",
                "format": "time",
                "description": "Giờ gợi ý (HH:MM)"
            },
            "doctor_name": {
                "type": "string",
                "description": "Tên bác sĩ (nếu có)"
            },
            "reason": {
                "type": "string",
                "description": "Lý do khám"
            },
            "urgency": {
                "type": "string",
                "enum": ["routine", "soon_within_week", "urgent_within_24h"],
                "description": "Mức độ cấp thiết"
            }
        },
        "required": ["appointment_type", "reason"]
    }
)
```

**Confirmation Preview:**
```
Meto sẽ đặt lịch hẹn:
━━━━━━━━━━━━━━━━━━━━━━
🏥 Khám định kỳ đái tháo đường
👨‍⚕️ BS. Trần Minh Khoa
📅 Gợi ý: 5/7/2026 9:00 SA
📝 Kiểm tra HbA1c + tư vấn
━━━━━━━━━━━━━━━━━━━━━━
[✓ Lưu lịch] [Chọn ngày khác] [Hủy]
```

---

### Tool 05: `navigate_screen`

**Purpose:** Điều hướng user đến màn hình liên quan trong ứng dụng MetoCare.

```python
ToolDefinition(
    name="navigate_screen",
    display_name="Đi đến màn hình",
    description=(
        "Điều hướng user đến màn hình liên quan trong ứng dụng. "
        "Dùng khi Meto gợi ý user xem thêm thông tin ở màn hình cụ thể."
    ),
    version="1.0.0",
    requires_consent=False,   # Navigation không cần confirm
    permission_scope=["navigation:execute"],
    rate_limit_per_minute=20,
    available_on_screens=[],
    requires_context_blocks=[],
    parameters_schema={
        "type": "object",
        "properties": {
            "target_screen": {
                "type": "string",
                "enum": ["dashboard", "labs", "medications", "metrics", 
                         "nutrition", "care_plan", "profile", "reminders", "appointments"],
                "description": "Màn hình đích"
            },
            "entity_id": {
                "type": "string",
                "description": "ID của entity cụ thể cần xem (vd: lab result ID)"
            },
            "reason": {
                "type": "string",
                "description": "Lý do điều hướng (để UI hiển thị tooltip)"
            }
        },
        "required": ["target_screen", "reason"]
    }
)
```

**Implementation:**
```python
async def navigate_screen_handler(
    user_id: str,
    target_screen: str,
    entity_id: str | None,
    reason: str,
    context: dict
) -> ToolResult:
    
    # Validate target screen is valid
    VALID_SCREENS = ["dashboard", "labs", "medications", "metrics", 
                     "nutrition", "care_plan", "profile", "reminders", "appointments"]
    if target_screen not in VALID_SCREENS:
        return ToolResult(success=False, error_code="invalid_screen")
    
    # Validate entity_id belongs to user (nếu có)
    if entity_id:
        ownership = await verify_entity_ownership(user_id, entity_id, target_screen)
        if not ownership:
            return ToolResult(success=False, error_code="entity_not_found")
    
    # Build navigation payload cho frontend
    nav_payload = {
        "screen": target_screen,
        "entity_id": entity_id,
        "reason": reason,
    }
    
    return ToolResult(
        success=True,
        data={"navigation": nav_payload},
        summary_for_prompt=f"Đã điều hướng user đến màn hình {target_screen}."
    )
```

**Frontend Handling:**
```typescript
// Khi nhận navigation event từ Meto
case 'tool_result':
  if (event.tool_name === 'navigate_screen' && event.data.navigation) {
    // Show navigation prompt
    showNavigationPrompt({
      screen: event.data.navigation.screen,
      reason: event.data.navigation.reason,
      onConfirm: () => router.push(`/${event.data.navigation.screen}`)
    })
  }
```

---

### Tool 06: `update_care_plan`

**Purpose:** Đánh dấu task hoàn thành trong care plan từ cuộc trò chuyện.

```python
ToolDefinition(
    name="update_care_plan",
    display_name="Cập nhật kế hoạch chăm sóc",
    description=(
        "Đánh dấu hoàn thành một task trong kế hoạch chăm sóc. "
        "Dùng khi user báo cáo đã uống thuốc, đo chỉ số, hay hoàn thành task."
    ),
    version="1.0.0",
    requires_consent=True,
    permission_scope=["care_plan:write"],
    rate_limit_per_minute=5,
    available_on_screens=[],
    requires_context_blocks=["current_care_plan"],
    parameters_schema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "UUID của task cần cập nhật"
            },
            "task_title": {
                "type": "string",
                "description": "Tên task (dùng để lookup nếu không có task_id)"
            },
            "new_status": {
                "type": "string",
                "enum": ["completed", "skipped", "postponed"],
                "description": "Trạng thái mới của task"
            },
            "completion_note": {
                "type": "string",
                "description": "Ghi chú kèm theo (vd: 'Đo lúc 7:30, kết quả 132')"
            },
            "completed_at": {
                "type": "string",
                "format": "date-time",
                "description": "Thời gian hoàn thành (mặc định: now)"
            }
        },
        "required": ["new_status"]
    }
)
```

**Confirmation Preview:**
```
Đánh dấu hoàn thành:
━━━━━━━━━━━━━━━━━━━
✅ Uống Metformin 500mg buổi trưa
📅 Hôm nay, 12:05
━━━━━━━━━━━━━━━━━━━
[✓ Xác nhận] [Hủy]
```

---

### Tool 07: `record_metric`

**Purpose:** Ghi nhận chỉ số sức khỏe mà user đề cập trong chat.

```python
ToolDefinition(
    name="record_metric",
    display_name="Ghi chỉ số sức khỏe",
    description=(
        "Ghi nhận chỉ số sức khỏe từ chat. "
        "Dùng khi user nói 'huyết áp hôm nay 130/85' hoặc 'đường huyết sáng 145'."
    ),
    version="1.0.0",
    requires_consent=True,
    permission_scope=["metrics:write"],
    rate_limit_per_minute=10,
    available_on_screens=[],
    requires_context_blocks=[],
    parameters_schema={
        "type": "object",
        "properties": {
            "metric_type": {
                "type": "string",
                "enum": ["blood_pressure", "glucose", "weight", "spo2", 
                         "heart_rate", "temperature", "bmi"],
                "description": "Loại chỉ số"
            },
            "value": {
                "type": "string",
                "description": "Giá trị đo được (vd: '130/85' cho huyết áp)"
            },
            "unit": {
                "type": "string",
                "description": "Đơn vị (mmHg, mg/dL, kg, %, bpm, °C)"
            },
            "measured_at": {
                "type": "string",
                "format": "date-time",
                "description": "Thời điểm đo (mặc định: now)"
            },
            "context": {
                "type": "string",
                "enum": ["fasting", "post_meal", "post_exercise", "resting", "other"],
                "description": "Ngữ cảnh khi đo"
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú thêm"
            }
        },
        "required": ["metric_type", "value", "unit"]
    }
)
```

**Value Validation:**
```python
METRIC_VALIDATION_RULES = {
    "blood_pressure": {
        "format": r"^\d{2,3}/\d{2,3}$",
        "systolic_range": (50, 300),
        "diastolic_range": (30, 200),
    },
    "glucose": {
        "unit": "mg/dL",
        "range": (10, 1000),
        "critical_high": 400,
        "critical_low": 50,
    },
    "weight": {
        "unit": "kg",
        "range": (1, 500),
    },
    "spo2": {
        "unit": "%",
        "range": (50, 100),
        "critical_low": 90,
    },
}

async def validate_metric(metric_type: str, value: str) -> ValidationResult:
    """Validate giá trị + check nếu giá trị critical → trigger safety check"""
    ...
```

---

### Tool 08: `generate_health_summary`

**Purpose:** Tạo tóm tắt hồ sơ sức khỏe tổng quan cho user xem hoặc chia sẻ với bác sĩ.

```python
ToolDefinition(
    name="generate_health_summary",
    display_name="Tóm tắt hồ sơ sức khỏe",
    description=(
        "Tạo tóm tắt tổng quan hồ sơ sức khỏe của user. "
        "Bao gồm chẩn đoán chính, thuốc, chỉ số gần nhất, và kết quả xét nghiệm."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["health_summary:generate", "labs:read", "medications:read", "metrics:read"],
    rate_limit_per_minute=2,
    rate_limit_per_hour=5,
    available_on_screens=[],
    requires_context_blocks=["health_summary", "active_medications", "recent_labs", "recent_metrics"],
    parameters_schema={
        "type": "object",
        "properties": {
            "summary_type": {
                "type": "string",
                "enum": ["brief", "detailed", "doctor_ready"],
                "description": "Loại tóm tắt: tóm tắt / chi tiết / để mang đến bác sĩ"
            },
            "time_period": {
                "type": "string",
                "enum": ["this_week", "this_month", "last_3_months", "all_time"],
                "description": "Khoảng thời gian cần tóm tắt"
            },
            "include_sections": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["diagnoses", "medications", "labs", "metrics", "care_plan", "appointments"]
                },
                "description": "Sections cần include trong tóm tắt"
            }
        },
        "required": ["summary_type"]
    }
)
```

---

### Tool 09: `nutrition_recommendation`

**Purpose:** Gợi ý dinh dưỡng phù hợp với tình trạng sức khỏe của user. **KHÔNG prescribing diet.**

```python
ToolDefinition(
    name="nutrition_recommendation",
    display_name="Gợi ý dinh dưỡng",
    description=(
        "Cung cấp gợi ý dinh dưỡng chung phù hợp với tình trạng sức khỏe. "
        "KHÔNG kê thực đơn cụ thể, KHÔNG thay thế tư vấn dinh dưỡng chuyên nghiệp."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["health_summary:generate"],
    rate_limit_per_minute=5,
    available_on_screens=["nutrition", "dashboard"],
    requires_context_blocks=["health_summary", "recent_metrics"],
    parameters_schema={
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["food_to_eat", "food_to_avoid", "meal_timing", "nutrient_focus"],
                "description": "Loại câu hỏi dinh dưỡng"
            },
            "specific_food": {
                "type": "string",
                "description": "Thực phẩm cụ thể user muốn hỏi (vd: 'cơm trắng', 'chuối')"
            },
            "meal_context": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snack"],
                "description": "Bữa ăn đang hỏi"
            }
        },
        "required": ["query_type"]
    }
)
```

**Safety Guardrails:**
- Chỉ cung cấp gợi ý dựa trên evidence-based general guidelines cho condition
- Luôn kèm: "Đây là gợi ý chung. Chế độ ăn cụ thể cần tham khảo chuyên gia dinh dưỡng."
- Không tạo meal plan cụ thể với calorie counting
- Không khuyên nhịn ăn hoặc kiêng ăn extreme

---

### Tool 10: `exercise_recommendation`

**Purpose:** Gợi ý vận động nhẹ phù hợp với tình trạng sức khỏe.

```python
ToolDefinition(
    name="exercise_recommendation",
    display_name="Gợi ý vận động",
    description=(
        "Gợi ý hoạt động thể chất nhẹ phù hợp với tình trạng sức khỏe. "
        "KHÔNG tạo training plan, KHÔNG gợi ý vận động cường độ cao khi không rõ tình trạng."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["health_summary:generate"],
    rate_limit_per_minute=5,
    available_on_screens=[],
    requires_context_blocks=["health_summary", "recent_metrics"],
    parameters_schema={
        "type": "object",
        "properties": {
            "activity_level": {
                "type": "string",
                "enum": ["sedentary", "light", "moderate", "active"],
                "description": "Mức hoạt động hiện tại của user"
            },
            "exercise_type": {
                "type": "string",
                "enum": ["walking", "stretching", "strength", "cardio", "any"],
                "description": "Loại vận động user quan tâm"
            },
            "duration_preference": {
                "type": "string",
                "enum": ["5-10min", "15-20min", "30min", "60min"],
                "description": "Thời gian vận động mong muốn"
            },
            "location": {
                "type": "string",
                "enum": ["home", "gym", "outdoor", "any"],
                "description": "Nơi tập"
            }
        }
    }
)
```

**Safety Guardrails:**
- Check recent_metrics: nếu blood pressure > 160/100 → khuyên hỏi bác sĩ trước khi tập
- Không gợi ý high-intensity exercise cho user có heart conditions
- Luôn kèm disclaimer về tham khảo bác sĩ trước khi bắt đầu routine mới

---

### Tool 11: `symptom_intake`

**Purpose:** Thu thập triệu chứng có cấu trúc từ cuộc trò chuyện để chuẩn bị cho buổi khám bác sĩ.

```python
ToolDefinition(
    name="symptom_intake",
    display_name="Ghi lại triệu chứng",
    description=(
        "Thu thập thông tin triệu chứng có cấu trúc: mô tả, thời gian bắt đầu, "
        "mức độ, yếu tố làm nặng/nhẹ hơn. Tạo bản tóm tắt để mang đến bác sĩ. "
        "KHÔNG chẩn đoán bệnh từ triệu chứng."
    ),
    version="1.0.0",
    requires_consent=True,
    permission_scope=["symptom:collect"],
    rate_limit_per_minute=2,
    rate_limit_per_hour=5,
    available_on_screens=[],
    requires_context_blocks=["health_summary"],
    parameters_schema={
        "type": "object",
        "properties": {
            "symptom_description": {
                "type": "string",
                "description": "Mô tả triệu chứng từ user"
            },
            "onset": {
                "type": "string",
                "description": "Khi nào bắt đầu (vd: 'từ sáng nay', '3 ngày trước')"
            },
            "severity": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Mức độ nghiêm trọng (1-10)"
            },
            "location": {
                "type": "string",
                "description": "Vị trí triệu chứng (vd: 'ngực trái', 'bụng dưới')"
            },
            "aggravating_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Yếu tố làm nặng hơn"
            },
            "relieving_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Yếu tố làm nhẹ hơn"
            },
            "associated_symptoms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Triệu chứng đi kèm"
            }
        },
        "required": ["symptom_description"]
    }
)
```

**Safety Integration:**
```python
async def symptom_intake_handler(...) -> ToolResult:
    
    # CRITICAL: Check for emergency red flags trong symptom description
    has_emergency, severity, phrase = check_red_flags(symptom_description)
    
    if has_emergency and severity == "emergency":
        # Bypass tool execution → return escalation
        return ToolResult(
            success=True,
            data={"requires_emergency": True},
            summary_for_prompt=(
                f"CRITICAL: Triệu chứng '{phrase}' là dấu hiệu khẩn cấp. "
                "Cần escalation response ngay, không thu thập symptom intake."
            )
        )
    
    # Normal flow: collect structured symptom
    symptom_record = await symptom_service.create({
        "user_id": user_id,
        "description": symptom_description,
        "severity": severity,
        # ... other fields
        "created_via": "meto_ai",
    })
    
    return ToolResult(
        success=True,
        data={"symptom_id": symptom_record.id},
        summary_for_prompt=(
            f"Đã ghi triệu chứng '{symptom_description}', "
            f"mức độ {severity}/10, bắt đầu {onset}. "
            "Tóm tắt sẵn sàng để mang đến bác sĩ."
        )
    )
```

---

### Tool 12: `prepare_doctor_questions`

**Purpose:** Tạo danh sách câu hỏi chuẩn bị cho lần khám bác sĩ tới, dựa trên tình trạng sức khỏe hiện tại.

```python
ToolDefinition(
    name="prepare_doctor_questions",
    display_name="Chuẩn bị câu hỏi cho bác sĩ",
    description=(
        "Tạo danh sách câu hỏi phù hợp để hỏi bác sĩ trong lần khám tới, "
        "dựa trên tình trạng sức khỏe, thuốc đang dùng, và kết quả xét nghiệm gần nhất."
    ),
    version="1.0.0",
    requires_consent=False,
    permission_scope=["health_summary:generate"],
    rate_limit_per_minute=3,
    available_on_screens=[],
    requires_context_blocks=["health_summary", "active_medications", "recent_labs", "today_context"],
    parameters_schema={
        "type": "object",
        "properties": {
            "appointment_type": {
                "type": "string",
                "enum": ["regular_checkup", "specialist", "follow_up", "new_symptoms"],
                "description": "Loại buổi khám"
            },
            "specific_concerns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Mối lo ngại cụ thể user muốn hỏi bác sĩ"
            },
            "include_categories": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["medications", "lab_results", "symptoms", "lifestyle", "treatment_plan"]
                },
                "description": "Danh mục câu hỏi cần include"
            }
        }
    }
)
```

**Output Format:**
```markdown
## Câu hỏi chuẩn bị cho BS. Trần Minh Khoa
*Khám định kỳ đái tháo đường — 5/7/2026*

### 📊 Về kết quả xét nghiệm
- HbA1c 7.8% — mục tiêu nên là bao nhiêu với trường hợp của tôi?
- Có cần điều chỉnh gì về chế độ điều trị không?

### 💊 Về thuốc
- Metformin đôi khi gây buồn nôn buổi sáng — có cách nào giảm không?
- Có cần thêm thuốc hoặc thay đổi liều không?

### 📈 Về chỉ số sức khỏe
- Huyết áp thường 140-150/90 — bình thường hay cần theo dõi thêm?

### 🏃 Về lối sống
- Vận động như thế nào là phù hợp với tình trạng hiện tại?
```

---

## 4. MCP Compatibility Design

Thiết kế để sau này có thể expose tools qua MCP (Model Context Protocol):

```python
class MCPToolAdapter:
    """
    Adapter để expose Meto tools qua MCP protocol
    Mỗi tool Meto = 1 MCP tool
    """
    
    @classmethod
    def to_mcp_schema(cls, tool: ToolDefinition) -> dict:
        return {
            "name": f"meto.{tool.name}",
            "description": tool.description,
            "inputSchema": {
                "type": "object",
                **tool.parameters_schema
            }
        }
    
    @classmethod
    def from_mcp_call(cls, mcp_request: dict) -> ToolCallRequest:
        tool_name = mcp_request["name"].replace("meto.", "")
        return ToolCallRequest(
            tool_name=tool_name,
            arguments=mcp_request["arguments"]
        )
```

---

## 5. Tool Engine Implementation

```python
# app/ai/tool_engine.py

class ToolEngine:
    
    async def process_tool_call(
        self,
        tool_call: dict,
        session: ConversationSession,
        context: dict,
        consent: UserConsent
    ) -> ToolResult:
        
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]
        
        # 1. Lookup tool
        tool_def = ToolRegistry.get(tool_name)
        if not tool_def:
            return ToolResult(success=False, error_code="tool_not_found")
        
        # 2. Permission check
        if not self._check_permissions(tool_def, consent):
            return ToolResult(
                success=False,
                error_code="permission_denied",
                user_facing_error=f"Anh/chị chưa cho phép Meto thực hiện hành động này."
            )
        
        # 3. Rate limit check
        if not await self._check_rate_limit(tool_name, session.user_id):
            return ToolResult(
                success=False,
                error_code="rate_limited",
                user_facing_error="Đã sử dụng tính năng này quá nhiều lần. Vui lòng chờ."
            )
        
        # 4. Validate arguments
        validation_result = validate_against_schema(arguments, tool_def.parameters_schema)
        if not validation_result.valid:
            return ToolResult(
                success=False,
                error_code="invalid_arguments",
                error_message=str(validation_result.errors)
            )
        
        # 5. Execute
        started_at = utcnow()
        try:
            result = await tool_def.handler(
                user_id=session.user_id,
                context=context,
                **arguments
            )
        except Exception as e:
            result = ToolResult(
                success=False,
                error_code="execution_error",
                error_message=str(e),
                user_facing_error="Có lỗi khi thực hiện. Vui lòng thử lại."
            )
        
        # 6. Audit log
        await audit_log_tool_call(
            user_id=session.user_id,
            session_id=session.session_id,
            tool_name=tool_name,
            result=result,
            duration_ms=(utcnow() - started_at).total_seconds() * 1000
        )
        
        return result
```

---

## 6. Acceptance Criteria

### AC-TOOL-001: Tool Registration
- [ ] Tất cả 12 tools được register khi app khởi động
- [ ] Tool schema valid theo OpenAI function calling format
- [ ] MCP compatibility verified cho mỗi tool

### AC-TOOL-002: Permission & Consent
- [ ] Tools yêu cầu per-action consent hiển thị confirmation UI trước khi execute
- [ ] Tools không có permission scope phù hợp bị block với error message rõ ràng
- [ ] Cross-user tool call bị block hoàn toàn (ToolResult error_code="permission_denied")

### AC-TOOL-003: Rate Limiting
- [ ] Rate limit được enforce per user per tool
- [ ] Rate limit header trả về trong response để frontend có thể disable button
- [ ] Rate limit reset sau đúng 1 phút / 1 giờ tùy rule

### AC-TOOL-004: Audit Log
- [ ] Mọi tool call (success + fail) đều có audit entry
- [ ] Audit không chứa raw health values
- [ ] Audit có thể query theo user + date range

### AC-TOOL-005: Tool-specific
- [ ] `explain_lab`: chỉ giải thích lab trong danh sách của user
- [ ] `create_reminder`: xác nhận medication exists trước khi create
- [ ] `record_metric`: validate value range + trigger safety check nếu critical
- [ ] `symptom_intake`: luôn check red flags trước khi collect
- [ ] `navigate_screen`: chỉ navigate đến VALID_SCREENS
- [ ] `update_care_plan`: xác nhận task_id belongs to user
- [ ] `nutrition_recommendation`: không cung cấp calorie-specific meal plan
- [ ] `exercise_recommendation`: check blood pressure trước khi recommend intensive exercise

### AC-TOOL-006: Error Handling
- [ ] Mọi tool error trả về user-friendly message bằng tiếng Việt
- [ ] Tool error không crash conversation engine
- [ ] Tool result được inject vào conversation history đúng format

---

*Xem thêm: 08_CONVERSATION_ENGINE.md (tool call trong conversation flow), 10_MEMORY_ENGINE.md (memory từ tool results), 04_SAFETY_PRIVACY.md (audit logging)*
