# Meto AI — Conversation Engine Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Conversation Engine là lớp điều phối trung tâm của Meto, chịu trách nhiệm quản lý vòng đời toàn bộ cuộc trò chuyện — từ khi người dùng gửi tin đầu tiên đến khi session kết thúc, bao gồm quản lý context window, nén hội thoại, streaming response, xử lý lỗi, và lưu trữ.

**File backend chính:**
- `app/ai/conversation_engine.py` — Core engine
- `app/ai/conversation_manager.py` — Session & lifecycle
- `app/ai/conversation_compressor.py` — Summarization & compression
- `app/models/conversation.py` — DB models

---

## 1. Conversation Lifecycle

### 1.1 State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONVERSATION STATE MACHINE                    │
│                                                                  │
│     ┌──────────┐     user_message      ┌──────────┐             │
│     │  IDLE    │ ─────────────────────▶│ THINKING │             │
│     └──────────┘                       └──────────┘             │
│          ▲                                  │                    │
│          │                    stream_start  │                    │
│          │ last_chunk                       ▼                    │
│          │                          ┌──────────────┐            │
│          └──────────────────────────│  STREAMING   │            │
│                                     └──────────────┘            │
│                                          │  │                   │
│                               user_sends │  │ provider_error    │
│                               new_msg    │  │                   │
│                                     ▼   │  ▼                    │
│                              ┌──────────────────┐               │
│                              │   CANCELLED      │               │
│                              └──────────────────┘               │
│                                                │                 │
│                                        ┌───────────┐            │
│                                        │   ERROR   │            │
│                                        └───────────┘            │
│                                                                  │
│  Idle 30 min ──▶ SOFT_CLOSED  ──▶ 24h ──▶ ARCHIVED             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Transition Rules

| Từ trạng thái | Sự kiện | Sang trạng thái | Hành động |
|---------------|---------|-----------------|-----------|
| IDLE | user_message | THINKING | Start context assembly |
| THINKING | stream_start | STREAMING | Begin SSE stream |
| THINKING | provider_error | ERROR | Log error, notify user |
| STREAMING | last_chunk | IDLE | Save message, update last_active |
| STREAMING | user_sends_new | CANCELLED | Cancel current stream, transition to THINKING |
| STREAMING | provider_error | ERROR | Save partial response (if any), notify |
| ERROR | user_message | THINKING | Retry with new message |
| CANCELLED | — | THINKING | Process new message immediately |
| IDLE | idle_30min | SOFT_CLOSED | Clear streaming state, keep session |
| SOFT_CLOSED | user_message | THINKING | Reactivate session |
| SOFT_CLOSED | idle_24h | ARCHIVED | Move to archive, release resources |
| ARCHIVED | user_opens | NEW | Create new conversation (link to archive) |

### 1.3 Lifecycle Stages

```
NEW ─────▶ ACTIVE ─────▶ IDLE ─────▶ SOFT_CLOSED ─────▶ ARCHIVED ─────▶ DELETED
  └── (created)  (exchanging)  (30min)   (24h no activity)  (90 days)     (hard delete)
```

- **NEW:** Session được tạo, disclaimer được gửi, context được load
- **ACTIVE:** Đang có tin nhắn qua lại (user ↔ Meto)
- **IDLE:** Cuộc trò chuyện dừng nhưng chưa đóng (< 30 phút)
- **SOFT_CLOSED:** 30 phút không hoạt động; session vẫn visible trong history
- **ARCHIVED:** 24 giờ không hoạt động; move to archive storage
- **DELETED:** Xóa theo retention policy (90 ngày) hoặc user request

---

## 2. Session Management

### 2.1 Session Data Model

```python
class ConversationSession:
    session_id: str          # UUID v4, opaque token — không sequential
    user_id: str             # UUID từ JWT, không từ request body
    screen_id: str           # "dashboard|labs|medications|metrics|care_plan|nutrition|profile"
    entity_id: str | None    # ID của entity đang xem (vd: lab_result_id)
    
    # Lifecycle
    created_at: datetime
    last_active: datetime
    soft_closed_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None
    
    # Status
    status: ConversationStatus  # NEW | ACTIVE | IDLE | SOFT_CLOSED | ARCHIVED | DELETED
    current_state: ConversationState  # IDLE | THINKING | STREAMING | ERROR | CANCELLED
    
    # Context
    initial_context_snapshot: dict  # Context tại thời điểm bắt đầu session
    context_version: int            # Tăng khi context được refresh
    
    # Token tracking
    total_tokens_used: int
    message_count: int
    
    # TTL
    ttl_seconds: int = 86400  # 24 giờ → archived; sau 90 ngày → deleted
```

### 2.2 Session Creation

```python
async def create_session(
    user_id: str,
    screen_id: str,
    entity_id: str | None = None
) -> ConversationSession:
    session = ConversationSession(
        session_id=str(uuid4()),
        user_id=user_id,
        screen_id=screen_id,
        entity_id=entity_id,
        created_at=utcnow(),
        last_active=utcnow(),
        status=ConversationStatus.NEW,
        current_state=ConversationState.IDLE,
    )
    
    # Load & snapshot initial context
    context = await context_engine.assemble(user_id, screen_id)
    session.initial_context_snapshot = context
    
    # Store in Redis (hot) + PostgreSQL (persistent)
    await redis.setex(f"session:{session.session_id}", 86400, session.json())
    await db.insert("conversations", session.to_db_record())
    
    return session

async def detect_new_conversation(user_id: str, screen_id: str) -> bool:
    """
    New conversation khi:
    1. Không có active session trong 30 phút
    2. User chủ động tạo mới (button "Cuộc trò chuyện mới")
    3. Screen thay đổi đáng kể (dashboard → labs)
    4. Session bị archived/deleted
    """
    last_session = await get_last_session(user_id)
    if not last_session:
        return True
    if last_session.status in (ARCHIVED, DELETED):
        return True
    if last_session.last_active < utcnow() - timedelta(minutes=30):
        return True
    return False
```

### 2.3 Session Expiry & Cleanup

```python
# Chạy mỗi 5 phút bởi background worker
async def cleanup_sessions():
    # Soft close sessions idle > 30 phút
    await db.execute("""
        UPDATE conversations 
        SET status = 'SOFT_CLOSED', soft_closed_at = NOW()
        WHERE status = 'ACTIVE' 
          AND last_active < NOW() - INTERVAL '30 minutes'
    """)
    
    # Archive sessions soft-closed > 24 giờ
    await db.execute("""
        UPDATE conversations 
        SET status = 'ARCHIVED', archived_at = NOW()
        WHERE status = 'SOFT_CLOSED'
          AND soft_closed_at < NOW() - INTERVAL '24 hours'
    """)
    
    # Soft-delete archived > 90 ngày (hard delete sau 7 ngày)
    await db.execute("""
        UPDATE conversations 
        SET status = 'DELETED', deleted_at = NOW()
        WHERE status = 'ARCHIVED'
          AND archived_at < NOW() - INTERVAL '90 days'
    """)
```

---

## 3. Context Window Strategy

### 3.1 Token Budget Allocation

Tổng context window: **128,000 tokens** (Claude Sonnet 3.7)

| Slot | Component | Token Budget | Ghi chú |
|------|-----------|-------------|---------|
| System Prompt | Fixed instruction | 2,000 | Không thay đổi |
| Developer Prompt | Personalization | 500 | Thay đổi per-user |
| Context Blocks | 9 blocks từ Context Engine | 2,000 | Xem 02_CONTEXT_ENGINE.md |
| Memory Injection | Top-K memories | 500 | Từ Memory Engine |
| Tool Definitions | Tool schema | 1,000 | Khi tools enabled |
| Conversation History | Compressed messages | 10,000 | Dynamic — xem 3.2 |
| User Message (current) | Input | 2,000 | Max per message |
| **Response Budget** | **AI output** | **4,000** | Meto's answer |
| Safety Buffer | Padding | 1,000 | Tránh truncation |
| **TOTAL** | | **23,000** | Để room cho context growth |

**Lưu ý:** Với Claude Sonnet, tổng token per request giữ ở 23K để đảm bảo response quality. Nếu provider là OpenAI (gpt-4o), window là 128K — dùng budget tương tự để nhất quán.

### 3.2 Sliding Window — Conversation History

```
┌────────────────────────────────────────────────────────────┐
│          CONVERSATION HISTORY (max 10,000 tokens)          │
│                                                            │
│  [Oldest]                                     [Newest]    │
│  ┌──────────────┐ ┌──────────┐ ┌───────────────────────┐  │
│  │  SUMMARY     │ │ DROPPED  │ │  RECENT MESSAGES      │  │
│  │ (compressed) │ │ (evicted)│ │  (last N turns kept)  │  │
│  └──────────────┘ └──────────┘ └───────────────────────┘  │
│  ~1,000 tokens                    ~9,000 tokens           │
└────────────────────────────────────────────────────────────┘
```

**Drop Priority (eviction order — oldest first):**
1. System messages / disclaimers cũ (chỉ giữ 1 bản mới nhất)
2. Tool calls / tool results đã xử lý xong
3. User messages rất ngắn (< 10 tokens) không chứa health context
4. Meto responses có độ lặp lại cao (similarity > 0.9 với messages khác)
5. Bất kỳ message nào ngoài 20 turns gần nhất

**Luôn giữ:**
- Turn đầu tiên (first_turn_system_context)
- Bất kỳ message có safety escalation
- Bất kỳ message có critical health values
- Summary của phần đã drop

### 3.3 Context Refresh Policy

```python
CONTEXT_REFRESH_TRIGGERS = [
    "screen_changed",           # User navigate sang màn khác
    "entity_changed",           # Đang xem lab result khác
    "metrics_updated",          # Có số đo mới trong session
    "care_plan_updated",        # Task được check off
    "session_turn_count >= 5",  # Refresh mỗi 5 turns để cập nhật
]

async def should_refresh_context(session: Session, current_request: Request) -> bool:
    if current_request.screen_id != session.last_screen_id:
        return True
    if current_request.entity_id != session.last_entity_id:
        return True
    if session.message_count % 5 == 0:
        return True
    return False
```

---

## 4. Conversation Summarization

### 4.1 Khi Nào Summarize

```python
SUMMARIZATION_TRIGGERS = {
    "turn_count": 15,          # Sau 15 turns
    "token_count": 8000,        # Khi history đạt 8K tokens
    "session_end": True,        # Khi session SOFT_CLOSED
    "explicit_user": True,      # User yêu cầu "tóm tắt cuộc trò chuyện"
}
```

### 4.2 Summarization Prompt

```python
SUMMARIZATION_SYSTEM_PROMPT = """
Bạn là hệ thống tóm tắt cuộc trò chuyện y tế. 
Tạo tóm tắt ngắn gọn (max 200 words) theo format sau:

## Tóm tắt cuộc trò chuyện

**Thời gian:** {start_time} → {end_time}
**Chủ đề chính:** [bullet list 2-4 topics]

**Thông tin sức khỏe đề cập:**
- [List các chỉ số, thuốc, kết quả xét nghiệm được đề cập]

**Hành động đã ghi nhận:**
- [Bất kỳ hành động nào user thực hiện (uống thuốc, đo chỉ số, đặt lịch)]

**Mối lo ngại / câu hỏi chưa giải quyết:**
- [Nếu có]

**Lưu ý cho cuộc trò chuyện tiếp:**
- [Context quan trọng cần nhớ]

QUAN TRỌNG: Chỉ tóm tắt thông tin y tế. Không suy luận, không chẩn đoán.
"""
```

### 4.3 Summary Storage & Injection

```python
class ConversationSummary:
    id: str
    conversation_id: str
    user_id: str
    
    summary_text: str           # Nội dung tóm tắt
    messages_covered: int       # Số turns được compress
    tokens_original: int        # Tokens trước khi compress
    tokens_summary: int         # Tokens sau khi compress
    compression_ratio: float    # = tokens_summary / tokens_original
    
    topics: list[str]           # Chủ đề chính
    health_items_mentioned: list[dict]  # Structured health data
    actions_recorded: list[str]
    
    created_at: datetime
    turn_range: tuple[int, int]  # (first_turn, last_turn) được cover

# Injection vào context (đầu phần history):
HISTORY_INJECTION_FORMAT = """
## Tóm tắt cuộc trò chuyện trước đó
{summary_text}

---
## Tiếp tục cuộc trò chuyện (từ tin nhắn gần đây):
"""
```

---

## 5. Long Conversation Compression

### 5.1 Compression Threshold

| Điều kiện | Action |
|-----------|--------|
| History < 5,000 tokens | Không làm gì |
| History 5,000–8,000 tokens | Lazy compress: drop oldest 20% |
| History > 8,000 tokens | Active compress: summarize + drop |
| history > 9,500 tokens (emergency) | Hard truncate to 7,000 |

### 5.2 Compression Algorithm

```python
async def compress_conversation_history(
    messages: list[Message],
    target_tokens: int = 7000
) -> tuple[list[Message], ConversationSummary | None]:
    
    current_tokens = count_tokens(messages)
    
    if current_tokens <= 5000:
        return messages, None
    
    # Identify messages to summarize (oldest 40%)
    split_point = int(len(messages) * 0.4)
    to_summarize = messages[:split_point]
    to_keep = messages[split_point:]
    
    # Generate summary via AI (mini call)
    summary = await generate_summary(to_summarize)
    
    # Rebuild: [summary_block] + [kept_messages]
    summary_message = Message(
        role="system",
        content=f"[CONVERSATION SUMMARY]\n{summary.summary_text}",
        is_summary=True,
        covers_turns=summary.turn_range
    )
    
    compressed = [summary_message] + to_keep
    
    # Verify we're within budget
    if count_tokens(compressed) > target_tokens:
        # Emergency: hard truncate to_keep
        compressed = hard_truncate(compressed, target_tokens)
    
    return compressed, summary
```

### 5.3 Lossless vs Lossy

| Loại thông tin | Compression strategy |
|----------------|---------------------|
| Safety escalation messages | **LOSSLESS** — giữ nguyên, không compress |
| Health values đề cập | **LOSSLESS** — inject vào summary structured |
| Casual Q&A | **LOSSY** — chỉ giữ topic |
| Tool calls / results | **SEMI-LOSSY** — giữ kết quả, drop intermediate steps |
| Disclaimers / system messages | **REPLACEABLE** — drop, inject fresh disclaimer |

### 5.4 User Notification

```python
# Khi compression diễn ra, gửi subtle UI indicator
COMPRESSION_UI_MESSAGE = {
    "type": "system_notice",
    "text": "Cuộc trò chuyện này đã dài. Meto đang sử dụng tóm tắt thông minh để nhớ nội dung quan trọng.",
    "style": "subtle",  # Non-intrusive, small text
    "dismissible": True
}
```

---

## 6. Token Budget Strategy — Per Request

### 6.1 Budget Allocation per Request

```python
class TokenBudget:
    SYSTEM_FIXED = 2000          # System + Developer prompt
    CONTEXT_DYNAMIC = 2000       # 9 context blocks (xem Context Engine)
    MEMORY_INJECTION = 500       # Top-K memories
    TOOL_DEFINITIONS = 1000      # Tool schemas (khi enabled)
    HISTORY_COMPRESSED = 10000   # Conversation history (sau compression)
    USER_MESSAGE_MAX = 2000      # Current user message
    RESPONSE_RESERVE = 4000      # Space cho Meto's response
    SAFETY_BUFFER = 1000         # Headroom

    TOTAL_REQUEST_BUDGET = (
        SYSTEM_FIXED + CONTEXT_DYNAMIC + MEMORY_INJECTION +
        TOOL_DEFINITIONS + HISTORY_COMPRESSED + USER_MESSAGE_MAX +
        RESPONSE_RESERVE + SAFETY_BUFFER
    )  # = 23,500 tokens

def allocate_tokens(session: Session, user_message: str) -> TokenAllocation:
    """Dynamic allocation — sacrifice history first"""
    user_msg_tokens = count_tokens(user_message)
    
    # Clamp user message
    if user_msg_tokens > 2000:
        # Truncate user message và notify
        user_message = truncate_to_tokens(user_message, 2000)
        user_msg_tokens = 2000
    
    # Calculate available for history
    fixed_cost = SYSTEM_FIXED + CONTEXT_DYNAMIC + MEMORY_INJECTION + RESPONSE_RESERVE + SAFETY_BUFFER
    history_budget = TOTAL_REQUEST_BUDGET - fixed_cost - user_msg_tokens
    
    return TokenAllocation(
        system=SYSTEM_FIXED,
        context=CONTEXT_DYNAMIC,
        memory=MEMORY_INJECTION,
        history=min(history_budget, HISTORY_COMPRESSED),
        user_message=user_msg_tokens,
        response=RESPONSE_RESERVE
    )
```

---

## 7. Streaming Response (SSE)

### 7.1 Protocol

Meto dùng **Server-Sent Events (SSE)** để stream response về frontend.

```
POST /api/ai/chat
→ Response: Content-Type: text/event-stream; charset=utf-8
            Cache-Control: no-cache
            Connection: keep-alive
            X-Accel-Buffering: no
```

### 7.2 Event Types

```typescript
// SSE Event format
type MetoSSEEvent =
  | { type: "start"; session_id: string; message_id: string }
  | { type: "chunk"; delta: string; index: number }
  | { type: "tool_call"; tool_name: string; status: "executing" | "done" }
  | { type: "done"; message_id: string; token_usage: TokenUsage }
  | { type: "error"; code: string; message: string; retry_after_ms?: number }
  | { type: "cancelled"; reason: string }
```

### 7.3 Chunk Format

```
data: {"type":"start","session_id":"...","message_id":"msg_xyz123"}

data: {"type":"chunk","delta":"Xin chào","index":0}
data: {"type":"chunk","delta":" anh! ","index":1}
data: {"type":"chunk","delta":"HbA1c 7.8%","index":2}
...
data: {"type":"done","message_id":"msg_xyz123","token_usage":{"input":1850,"output":320}}

```

### 7.4 Backend Streaming Implementation

```python
async def stream_response(
    session: Session,
    user_message: str,
    context: dict
) -> AsyncGenerator[str, None]:
    
    # Notify state change
    session.current_state = ConversationState.THINKING
    await update_session_state(session)
    
    # Assemble prompt
    messages = await build_messages(session, context, user_message)
    
    # Emit start event
    yield sse_event("start", {
        "session_id": session.session_id,
        "message_id": new_message_id()
    })
    
    session.current_state = ConversationState.STREAMING
    
    collected_chunks = []
    
    try:
        async for chunk in ai_provider.stream(messages):
            if session.current_state == ConversationState.CANCELLED:
                yield sse_event("cancelled", {"reason": "user_interrupted"})
                return
            
            collected_chunks.append(chunk)
            yield sse_event("chunk", {
                "delta": chunk.text,
                "index": len(collected_chunks)
            })
        
        # Save complete message
        full_response = "".join(collected_chunks)
        await save_message(session, role="assistant", content=full_response)
        
        session.current_state = ConversationState.IDLE
        yield sse_event("done", {
            "message_id": session.last_message_id,
            "token_usage": chunk.usage
        })
        
    except ProviderError as e:
        session.current_state = ConversationState.ERROR
        yield sse_event("error", {
            "code": e.code,
            "message": get_user_friendly_error(e),
            "retry_after_ms": e.retry_after_ms
        })
```

### 7.5 Frontend Consumption

```typescript
// hooks/useMetoStream.ts
export function useMetoStream() {
  const [chunks, setChunks] = useState<string[]>([])
  const [status, setStatus] = useState<StreamStatus>('idle')
  const abortRef = useRef<(() => void) | null>(null)

  const sendMessage = useCallback(async (message: string, sessionId: string) => {
    setStatus('thinking')
    setChunks([])

    const { stream, cancel } = await createSSEStream('/api/ai/chat', {
      message,
      session_id: sessionId,
    })
    abortRef.current = cancel

    for await (const event of stream) {
      switch (event.type) {
        case 'start':
          setStatus('streaming')
          break
        case 'chunk':
          setChunks(prev => [...prev, event.delta])
          break
        case 'done':
          setStatus('idle')
          abortRef.current = null
          break
        case 'error':
          setStatus('error')
          break
        case 'cancelled':
          setStatus('idle')
          break
      }
    }
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.()
    setStatus('idle')
  }, [])

  return { chunks, status, sendMessage, cancel }
}
```

---

## 8. Interrupt / Cancel Response

### 8.1 Cancel Strategy

Khi user gửi tin mới trong khi Meto đang streaming:

```python
class CancelStrategy:
    """
    1. Frontend: Abort SSE connection ngay lập tức
    2. Backend: Nhận cancel signal, set session.current_state = CANCELLED
    3. Stream generator check CANCELLED state mỗi chunk — exit ngay
    4. Save partial response với flag is_partial=True
    5. Start processing new message
    """

async def handle_new_message_during_stream(
    session: Session,
    new_message: str
) -> None:
    # Signal cancel to active stream
    session.current_state = ConversationState.CANCELLED
    await update_session_state(session)
    
    # Brief wait for stream to notice
    await asyncio.sleep(0.05)
    
    # Process new message (stream sẽ exit khi thấy CANCELLED)
    await process_message(session, new_message)
```

### 8.2 Partial Response Handling

```python
class PartialResponsePolicy:
    # Nếu partial response >= 50 tokens: lưu với flag is_partial=True
    MIN_TOKENS_TO_SAVE = 50
    
    # Không inject partial response vào context window của request tiếp theo
    # (tránh confuse model với câu trả lời dang dở)
    INJECT_PARTIAL_INTO_HISTORY = False
    
    # UI: Hiện [bị gián đoạn] badge trên tin nhắn partial
    UI_PARTIAL_INDICATOR = True
```

---

## 9. Multi-Turn Reasoning Coherence

### 9.1 Coherence Strategy

Meto duy trì coherence qua nhiều turns bằng:

1. **Compressed history** — Các turns cũ được compress, giữ context quan trọng
2. **Summary injection** — Summary của cuộc trò chuyện được inject đầu mỗi request
3. **Entity tracking** — Theo dõi entities (thuốc, lab, chỉ số) đã đề cập
4. **Topic thread** — Duy trì "thread" chủ đề trong session

```python
class CoherenceManager:
    async def build_coherence_context(
        self, session: Session
    ) -> dict:
        """
        Build additional coherence context cho mỗi request:
        - entities_mentioned: drugs, labs, metrics discussed this session
        - open_questions: user questions not yet fully answered
        - pending_actions: actions Meto suggested but not confirmed
        """
        return {
            "entities_mentioned": await self.extract_entities(session),
            "open_questions": await self.find_open_questions(session),
            "pending_actions": await self.get_pending_actions(session),
            "session_topics": await self.summarize_topics(session),
        }
```

### 9.2 Reference Resolution

```python
# Khi user nói "nó" / "cái đó" / "kết quả đó"
async def resolve_references(
    user_message: str, 
    session: Session
) -> str:
    """
    Nếu message chứa pronoun references, resolve to explicit entities
    từ conversation history trước khi build prompt.
    
    "Kết quả đó có nghĩa gì?" → "Kết quả HbA1c 7.8% đó có nghĩa gì?"
    """
    ...
```

---

## 10. Error Recovery

### 10.1 Error Types & Recovery

| Error Type | Nguyên nhân | Recovery Strategy | User Message |
|------------|-------------|------------------|--------------|
| `provider_timeout` | AI provider không response sau 30s | Retry 1x, nếu fail → fallback | "Meto đang xử lý chậm một chút. Đang thử lại..." |
| `provider_error_500` | Internal server error từ provider | Fallback Claude→OpenAI | "Có sự cố nhỏ. Meto đang kết nối lại..." |
| `context_assembly_fail` | Lỗi load context từ DB | Retry 1x với empty context (safe mode) | "Meto chưa load được thông tin sức khỏe. Trả lời theo thông tin chung." |
| `rate_limit_exceeded` | 429 từ provider | Exponential backoff, fallback | "Meto đang bận. Vui lòng thử lại sau vài giây." |
| `network_error` | SSE connection dropped | Frontend auto-reconnect | "Kết nối bị gián đoạn. Đang kết nối lại..." |
| `token_limit_exceeded` | Message quá dài | Truncate + notify | "Tin nhắn của anh/chị quá dài. Meto đã rút gọn để xử lý." |
| `context_isolation_error` | Cross-user access attempt | Hard fail, alert | KHÔNG hiện thông tin — log security event |
| `safety_system_error` | Safety check crash | Default to escalation template | Dùng fallback escalation response |

### 10.2 User-Facing Error Messages

```python
USER_FRIENDLY_ERRORS = {
    "provider_timeout": "Meto đang xử lý chậm. {preferred_address} thử hỏi lại nhé?",
    "provider_error": "Có trục trặc nhỏ. Meto sẽ thử lại ngay.",
    "rate_limited": "Meto đang phục vụ nhiều người. Vui lòng chờ {retry_seconds} giây.",
    "context_fail": "Meto chưa đọc được hồ sơ sức khỏe lúc này. Meto vẫn có thể trả lời câu hỏi chung.",
    "message_too_long": "Tin nhắn hơi dài — {preferred_address} có thể hỏi ngắn gọn hơn được không?",
    "unknown": "Có lỗi không mong muốn. Nếu {preferred_address} cần gấp, hãy liên hệ bác sĩ trực tiếp.",
}
```

---

## 11. Retry Policy

```python
class RetryPolicy:
    MAX_RETRIES = 2                   # Tối đa 2 lần retry
    BASE_DELAY_MS = 1000              # 1 giây
    BACKOFF_MULTIPLIER = 2.0          # Exponential
    MAX_DELAY_MS = 10000             # Tối đa 10 giây delay
    
    FALLBACK_AFTER_RETRY_N = 1       # Sau 1 retry fail → switch provider
    
    # Conditions để retry (không retry tất cả errors)
    RETRYABLE_ERRORS = [
        "timeout",
        "server_error_500",
        "server_error_503",
        "rate_limit_429",  # Nhưng phải honor Retry-After header
    ]
    
    NON_RETRYABLE = [
        "auth_error_401",
        "content_policy_violation",
        "context_too_long",           # Phải compress trước rồi retry
        "context_isolation_error",    # Security — không retry
    ]

async def with_retry(fn: Coroutine, policy: RetryPolicy) -> Any:
    last_error = None
    for attempt in range(policy.MAX_RETRIES + 1):
        try:
            return await fn()
        except RetryableError as e:
            last_error = e
            if attempt == 0 and e.code in ["timeout", "server_error"]:
                # Sau lần đầu fail → fallback provider
                switch_to_fallback_provider()
            delay = min(
                policy.BASE_DELAY_MS * (policy.BACKOFF_MULTIPLIER ** attempt),
                policy.MAX_DELAY_MS
            )
            await asyncio.sleep(delay / 1000)
    raise MaxRetriesExceeded(last_error)
```

---

## 12. Idle Timeout

```python
IDLE_TIMEOUTS = {
    "soft_close_minutes": 30,     # 30 phút idle → soft close
    "archive_hours": 24,           # 24 giờ idle → archive
    "delete_days": 90,             # 90 ngày → soft delete (per retention policy)
    "hard_delete_days": 97,        # 7 ngày sau soft delete → hard delete
}

# Soft close notification (optional UI)
SOFT_CLOSE_UI_MESSAGE = {
    "type": "system_notice", 
    "text": "Cuộc trò chuyện đã tạm dừng. Nhắn tin để tiếp tục.",
    "style": "subtle",
    "show_after_minutes": 15  # Hint trước khi thực sự soft close
}
```

---

## 13. Persistence — DB Schema

### 13.1 Conversations Table

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      TEXT NOT NULL UNIQUE,  -- Opaque token, không phải UUID sequence
    
    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'NEW',
    -- NEW | ACTIVE | IDLE | SOFT_CLOSED | ARCHIVED | DELETED
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    soft_closed_at  TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    
    -- Context
    screen_id       TEXT NOT NULL,
    entity_id       UUID,
    entity_type     TEXT,
    
    -- Stats
    message_count   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    has_summary     BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Metadata
    title           TEXT,   -- Auto-generated từ first message
    topics          TEXT[], -- Array of topic tags
    
    CONSTRAINT valid_status CHECK (
        status IN ('NEW','ACTIVE','IDLE','SOFT_CLOSED','ARCHIVED','DELETED')
    )
);

-- Indexes
CREATE INDEX idx_conversations_user_status ON conversations(user_id, status);
CREATE INDEX idx_conversations_last_active ON conversations(last_active);
CREATE INDEX idx_conversations_deleted ON conversations(deleted_at) WHERE deleted_at IS NOT NULL;
```

### 13.2 Messages Table

```sql
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    
    -- Content
    role            TEXT NOT NULL,  -- 'user' | 'assistant' | 'system' | 'tool'
    content         TEXT NOT NULL,
    
    -- Flags
    is_partial      BOOLEAN NOT NULL DEFAULT FALSE,   -- Bị cancel giữa chừng
    is_summary      BOOLEAN NOT NULL DEFAULT FALSE,   -- Là summary block
    is_escalation   BOOLEAN NOT NULL DEFAULT FALSE,   -- Là safety escalation
    
    -- Tracking
    turn_index      INTEGER NOT NULL,
    token_count     INTEGER,
    
    -- Tool info (nếu role = tool)
    tool_name       TEXT,
    tool_call_id    TEXT,
    
    -- Provider info
    provider        TEXT,           -- 'claude' | 'openai'
    model           TEXT,           -- 'claude-sonnet-4-5' | 'gpt-4o'
    latency_ms      INTEGER,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id, turn_index);
CREATE INDEX idx_messages_user ON messages(user_id, created_at);

-- Full-text search
ALTER TABLE messages ADD COLUMN search_vector TSVECTOR;
CREATE INDEX idx_messages_search ON messages USING GIN(search_vector);

-- Trigger để tự động update search_vector
CREATE TRIGGER messages_search_update
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION
    tsvector_update_trigger(search_vector, 'pg_catalog.simple', content);
```

### 13.3 Conversation Summaries Table

```sql
CREATE TABLE conversation_summaries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id),
    
    summary_text        TEXT NOT NULL,
    turn_range_start    INTEGER NOT NULL,
    turn_range_end      INTEGER NOT NULL,
    messages_covered    INTEGER NOT NULL,
    tokens_original     INTEGER,
    tokens_summary      INTEGER,
    
    topics              TEXT[],
    health_items        JSONB,          -- Structured health data mentioned
    actions_recorded    TEXT[],
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 14. Conversation Search

```python
class ConversationSearchService:
    """
    Hỗ trợ tìm kiếm trong lịch sử cuộc trò chuyện
    """
    
    async def search(
        self,
        user_id: str,
        query: str,
        filters: SearchFilters
    ) -> list[SearchResult]:
        
        results = []
        
        # 1. Full-text search trong messages content
        if filters.search_content:
            rows = await db.fetch("""
                SELECT 
                    m.id, m.content, m.created_at, m.turn_index,
                    c.id as conversation_id, c.title, c.screen_id,
                    ts_rank(m.search_vector, plainto_tsquery('pg_catalog.simple', :query)) as rank
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.user_id = :user_id
                  AND m.role = 'user'
                  AND c.status != 'DELETED'
                  AND m.search_vector @@ plainto_tsquery('pg_catalog.simple', :query)
                  AND (:date_from IS NULL OR m.created_at >= :date_from)
                  AND (:date_to IS NULL OR m.created_at <= :date_to)
                  AND (:screen_id IS NULL OR c.screen_id = :screen_id)
                ORDER BY rank DESC, m.created_at DESC
                LIMIT 20
            """, {"user_id": user_id, "query": query, **filters.dict()})
            results.extend(rows)
        
        # 2. Search by topic
        if filters.topic:
            topic_rows = await db.fetch("""
                SELECT id, title, created_at, topics
                FROM conversations
                WHERE user_id = :user_id
                  AND status != 'DELETED'
                  AND :topic = ANY(topics)
                ORDER BY created_at DESC
                LIMIT 10
            """, {"user_id": user_id, "topic": filters.topic})
            results.extend(topic_rows)
        
        return deduplicate_and_rank(results)
```

---

## 15. Conversation Export

```python
class ExportFormat(str, Enum):
    JSON = "json"
    PDF = "pdf"
    TXT = "txt"

class ConversationExportService:
    
    async def export(
        self,
        user_id: str,
        conversation_id: str,
        format: ExportFormat
    ) -> bytes:
        
        # Verify ownership
        conv = await get_conversation(conversation_id, user_id)
        
        messages = await get_messages(conversation_id)
        
        export_data = ConversationExport(
            exported_at=utcnow(),
            user_display_name=conv.user.display_name,
            conversation_id=conversation_id,
            screen_context=conv.screen_id,
            created_at=conv.created_at,
            message_count=len(messages),
            messages=[
                {
                    "turn": msg.turn_index,
                    "role": "Bạn" if msg.role == "user" else "Meto",
                    "content": msg.content,
                    "time": msg.created_at.isoformat(),
                }
                for msg in messages
                if not msg.is_summary  # Không export internal summaries
            ],
            disclaimer=(
                "Nội dung này chỉ mang tính tham khảo. "
                "Không thay thế tư vấn y tế chuyên nghiệp."
            )
        )
        
        # KHÔNG export:
        # - context blocks (sensitive health data)
        # - system prompts
        # - tool call internals
        # - session_id / user_id (privacy)
        
        if format == ExportFormat.JSON:
            return export_data.json(indent=2).encode()
        elif format == ExportFormat.PDF:
            return await render_pdf(export_data)
        elif format == ExportFormat.TXT:
            return render_txt(export_data).encode()
```

---

## 16. Conversation Delete

```python
class DeleteStrategy(str, Enum):
    SOFT = "soft"   # Mark deleted, giữ trong DB 7 ngày
    HARD = "hard"   # Xóa ngay lập tức (user request)

async def delete_conversation(
    user_id: str,
    conversation_id: str,
    strategy: DeleteStrategy = DeleteStrategy.SOFT
) -> None:
    
    # Verify ownership
    conv = await get_conversation(conversation_id, user_id)
    if conv.user_id != user_id:
        raise PermissionDeniedError()
    
    if strategy == DeleteStrategy.SOFT:
        await db.execute("""
            UPDATE conversations 
            SET status = 'DELETED', deleted_at = NOW()
            WHERE id = :id AND user_id = :user_id
        """, {"id": conversation_id, "user_id": user_id})
        
        # Messages cascade — vẫn accessible để user undo trong 24h
    
    elif strategy == DeleteStrategy.HARD:
        # Xóa messages trước (cascade hoặc explicit)
        await db.execute("DELETE FROM messages WHERE conversation_id = :id", {"id": conversation_id})
        await db.execute("DELETE FROM conversation_summaries WHERE conversation_id = :id", {"id": conversation_id})
        await db.execute("DELETE FROM conversations WHERE id = :id AND user_id = :user_id", 
                        {"id": conversation_id, "user_id": user_id})
    
    # Clear Redis cache
    await redis.delete(f"session:{conv.session_id}")
    
    # Audit log (không log content, chỉ log action)
    await audit_log(user_id, "conversation_deleted", {
        "conversation_id": conversation_id,
        "strategy": strategy,
        "message_count": conv.message_count
    })
```

---

## 17. Conversation Retention Policy

```python
RETENTION_POLICY = {
    "default_days": 90,                    # Mặc định 90 ngày
    "user_configurable": True,             # User có thể chỉnh trong Settings
    "user_min_days": 7,                    # Tối thiểu giữ 7 ngày
    "user_max_days": 365,                  # Tối đa 1 năm
    
    "exceptions": {
        "has_safety_escalation": "2_years",  # Cuộc trò chuyện có escalation: 2 năm
        "explicitly_starred": "indefinite",  # User đánh dấu: vô thời hạn (đến khi xóa)
    },
    
    "hard_delete_delay_days": 7,           # Sau soft delete: 7 ngày delay trước hard delete
}

# User-configurable retention setting
class RetentionSettings(BaseModel):
    user_id: str
    retention_days: int = 90
    auto_delete_enabled: bool = True
    updated_at: datetime
```

---

## 18. Sequence Diagrams

### 18.1 Happy Path — First Message

```
User                Frontend          Backend/API        ContextEngine    AI Provider
 │                      │                  │                   │               │
 │ Tap floating button  │                  │                   │               │
 │─────────────────────▶│                  │                   │               │
 │                      │ POST /ai/session │                   │               │
 │                      │─────────────────▶│                   │               │
 │                      │                  │ assemble_context() │               │
 │                      │                  │──────────────────▶│               │
 │                      │                  │  9 blocks (Redis+DB)│             │
 │                      │                  │◀──────────────────│               │
 │                      │ session_id, disclaimer               │               │
 │                      │◀─────────────────│                   │               │
 │ Disclaimer shown     │                  │                   │               │
 │◀─────────────────────│                  │                   │               │
 │                      │                  │                   │               │
 │ Type & send message  │                  │                   │               │
 │─────────────────────▶│                  │                   │               │
 │                      │ POST /ai/chat (SSE)                  │               │
 │                      │─────────────────▶│                   │               │
 │                      │                  │ check_red_flags() │               │
 │                      │                  │ build_messages()  │               │
 │                      │                  │ stream(messages)──────────────────▶│
 │                      │ event: start     │                   │               │
 │                      │◀─────────────────│                   │               │
 │                      │ event: chunk*N   │                   │               │
 │ Streaming text       │◀─────────────────│◀──────────────────────────────────│
 │◀─────────────────────│                  │                   │               │
 │                      │ event: done      │                   │               │
 │                      │◀─────────────────│                   │               │
 │ Full response shown  │                  │ save_message()    │               │
 │◀─────────────────────│                  │ update_audit_log()│               │
```

### 18.2 Error Path — Provider Timeout

```
User     Frontend     Backend       AI Provider
 │           │             │               │
 │ Send msg  │             │               │
 │──────────▶│             │               │
 │           │──────────────▶             │
 │           │             │ stream()──────▶
 │           │             │               │ [30s timeout]
 │           │             │ ProviderTimeout│
 │           │             │               │
 │           │             │ retry (1x)────▶
 │           │             │               │ [fail again]
 │           │             │               │
 │           │             │ switch to OpenAI fallback
 │           │             │──────────────────────────▶
 │           │ chunk*N     │                          │
 │           │◀────────────│◀──────────────────────────
 │ Response  │             │                          │
 │◀──────────│             │                          │
 │           │             │ log_fallback_event()     │
```

---

## 19. New Conversation Detection

```python
async def should_create_new_conversation(
    user_id: str,
    screen_id: str,
    entity_id: str | None,
    trigger: str  # "user_tap_new" | "auto" | "screen_change"
) -> bool:
    """
    Trigger conditions cho new conversation:
    """
    # 1. User explicit request
    if trigger == "user_tap_new":
        return True
    
    last_session = await get_last_session(user_id)
    
    # 2. No previous session
    if not last_session:
        return True
    
    # 3. Session is archived/deleted
    if last_session.status in (ARCHIVED, DELETED):
        return True
    
    # 4. More than 30 minutes idle
    if last_session.last_active < utcnow() - timedelta(minutes=30):
        return True
    
    # 5. Significant screen change
    SIGNIFICANT_SCREEN_CHANGES = {
        ("dashboard", "labs"),
        ("dashboard", "medications"),
        ("labs", "medications"),
        ("metrics", "labs"),
    }
    if (last_session.screen_id, screen_id) in SIGNIFICANT_SCREEN_CHANGES:
        return True
    
    # 6. Entity change on same screen type
    if (last_session.screen_id == screen_id and 
        last_session.entity_id != entity_id and 
        entity_id is not None):
        return True
    
    return False
```

---

## 20. Acceptance Criteria

### AC-CE-001: Session Creation
- [ ] Session được tạo trong < 200ms
- [ ] Session ID là opaque UUID, không sequential
- [ ] user_id lấy từ JWT, không từ request body
- [ ] Initial context snapshot được load và cache
- [ ] Disclaimer được gửi trong event đầu tiên

### AC-CE-002: Streaming
- [ ] First chunk arrive trong < 3 giây (TTFT)
- [ ] Chunks gửi đều đặn, không có pause > 2 giây giữa chunks
- [ ] SSE connection không timeout trước khi done event
- [ ] Frontend render text real-time không bị flash

### AC-CE-003: Token Budget
- [ ] Total tokens per request không vượt 23,500
- [ ] History bị compress khi > 8,000 tokens
- [ ] User message bị truncate khi > 2,000 tokens (với notification)
- [ ] Response có đủ space (>= 2,000 tokens response budget)

### AC-CE-004: Cancel/Interrupt
- [ ] Cancel signal được xử lý trong < 100ms
- [ ] Partial response được lưu với is_partial=True
- [ ] New message được process ngay sau cancel
- [ ] Không có race condition giữa stream và new message

### AC-CE-005: Error Recovery
- [ ] Provider timeout → retry 1x → fallback trong < 35 giây tổng
- [ ] Context assembly fail → safe mode (empty context) không crash
- [ ] Network error → SSE reconnect tự động trong < 3 giây
- [ ] User nhận error message thân thiện, không raw stack trace

### AC-CE-006: Idle Timeout
- [ ] Soft close sau đúng 30 phút idle
- [ ] Archive sau đúng 24 giờ
- [ ] Soft delete sau 90 ngày
- [ ] Redis cache được clear khi session archived

### AC-CE-007: Persistence
- [ ] Mọi message được persist trước khi done event được gửi
- [ ] Partial messages được persist với flag
- [ ] Search index được update trong < 5 giây sau message save
- [ ] Export download trong < 10 giây cho session < 100 messages

### AC-CE-008: Multi-turn Coherence
- [ ] References ("nó", "kết quả đó") được resolve đúng trong 3 turns gần nhất
- [ ] Conversation history > 15 turns được summarize trước khi send
- [ ] Summary injection không làm mất context quan trọng (kiểm tra qua test cases)

### AC-CE-009: Conversation Search
- [ ] Full-text search trả về kết quả trong < 500ms
- [ ] Search không cross-user (RLS enforced)
- [ ] Soft-deleted conversations không xuất hiện trong search

### AC-CE-010: Delete & Retention
- [ ] Soft delete immediate, hard delete sau 7 ngày
- [ ] User-initiated delete xóa ngay lập tức khỏi UI
- [ ] Cascade: delete conversation → delete messages + summaries
- [ ] Retention policy được apply bởi scheduled job, không quá 1 ngày trễ

---

*Xem thêm: 02_CONTEXT_ENGINE.md (context blocks), 10_MEMORY_ENGINE.md (memory injection), 09_TOOLS_AND_ACTIONS.md (tool calls trong conversation)*
