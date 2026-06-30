# Meto AI — Analytics Layer Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Analytics Layer của Meto đo lường toàn bộ hành vi người dùng, hiệu suất hệ thống, và chất lượng AI để đưa ra quyết định cải thiện dựa trên dữ liệu thực.

**Nguyên tắc analytics:**
- **Privacy by design:** Không có PII trong events, chỉ aggregated metrics
- **Action-oriented:** Mọi metric phải dẫn đến quyết định cụ thể
- **Real-time + Batch:** Real-time cho alerting, batch cho reporting
- **Transparency:** User biết data nào được collect (via Privacy Policy)

**Stack:**
- Event collection: **Azure Event Hubs** (high-throughput ingestion)
- Stream processing: **Azure Stream Analytics** (real-time aggregation)
- Storage: **Azure Data Explorer (Kusto)** (analytics queries) + PostgreSQL (operational)
- Dashboard: **Grafana** (internal) + custom admin dashboard
- Alerting: **Azure Monitor + PagerDuty**

---

## 1. Analytics Architecture

### 1.1 Event Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                      EVENT PIPELINE                             │
│                                                                 │
│  Frontend              Backend              Analytics           │
│  ────────              ───────              ─────────           │
│                                                                 │
│  [User Action]    →   [API Endpoint]   →   [Event Publisher]   │
│  tap_button           POST /ai/chat        events.publish()    │
│  open_chat            response stream      │                   │
│  send_message                              ▼                   │
│                                    [Azure Event Hubs]          │
│                                            │                   │
│                              ┌─────────────┴─────────────┐    │
│                              │                           │    │
│                     [Stream Analytics]          [Batch Job]   │
│                     (real-time aggregation)    (hourly/daily)  │
│                              │                           │    │
│                    [Kusto / ADX]               [Kusto / ADX]  │
│                    (hot data, 90 days)          (cold data, 2yr)│
│                              │                           │    │
│                     [Grafana Dashboards]    [Scheduled Reports] │
│                     [Alert Rules]           [A/B Experiment]   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Event Collection Strategy

| Nguồn | Collection Method | Latency |
|-------|-----------------|---------|
| Backend (Python) | Direct SDK call trong API handler | < 50ms |
| Frontend (Next.js) | Client-side event queue, batch send every 5s | ~5s |
| Stream processing | Azure Stream Analytics (tumbling window) | < 30s |
| Dashboard refresh | Grafana auto-refresh every 60s | ~60s |

---

## 2. Event Taxonomy

### 2.1 Naming Convention

```
{category}_{action}_{object}

Examples:
meto_chat_opened         ← category: meto, action: chat, object: opened
meto_message_sent        ← category: meto, action: message, object: sent
meto_tool_executed       ← category: meto, action: tool, object: executed
meto_session_completed   ← category: meto, action: session, object: completed
meto_feedback_submitted  ← category: meto, action: feedback, object: submitted
```

### 2.2 Required Fields (Tất cả events)

```python
class BaseEvent:
    # Mandatory — mọi event
    event_name: str                  # snake_case, following naming convention
    event_id: str                    # UUID v4, unique per event
    timestamp: datetime              # UTC, millisecond precision
    session_id: str                  # Meto conversation session ID
    app_version: str                 # "2.1.0" — app build version
    platform: str                    # "ios" | "android" | "web"
    screen_id: str                   # Current screen when event fired
    
    # Anonymized user dimension — NO PII
    user_cohort_id: str              # Hashed user_id — không reversible
    user_age_bracket: str            # "18-25" | "26-35" | "36-45" | "46-55" | "55+"
    user_gender_segment: str         # "male" | "female" | "other" | "unknown"
    user_health_segment: str         # "diabetes" | "hypertension" | "multiple" | "general"
    is_new_user: bool                # First 7 days
    
    # KHÔNG bao giờ include:
    # - user_id (raw)
    # - user_name
    # - health_values (blood glucose, HbA1c, etc.)
    # - medication names
    # - conversation content
    # - location data
```

### 2.3 Event Categories

```python
METO_EVENT_CATEGORIES = {
    # Conversation lifecycle
    "meto_chat_opened",
    "meto_chat_closed",
    "meto_message_sent",
    "meto_response_received",
    "meto_response_cancelled",
    "meto_session_completed",
    "meto_session_abandoned",
    
    # Quick prompts
    "meto_quickprompt_shown",
    "meto_quickprompt_tapped",
    "meto_quickprompt_dismissed",
    
    # Tools
    "meto_tool_triggered",
    "meto_tool_confirmed",
    "meto_tool_cancelled",
    "meto_tool_executed",
    "meto_tool_failed",
    
    # Memory
    "meto_memory_optin",
    "meto_memory_optout",
    "meto_memory_edited",
    "meto_memory_deleted",
    
    # Feedback
    "meto_feedback_thumbsup",
    "meto_feedback_thumbsdown",
    "meto_feedback_comment_submitted",
    
    # Escalation
    "meto_escalation_shown",
    "meto_escalation_call_tapped",
    
    # Provider / Technical
    "meto_provider_fallback",
    "meto_provider_error",
    "meto_provider_retry",
    
    # Safety
    "meto_safety_flag_triggered",
    "meto_red_flag_detected",
    
    # Export / Search
    "meto_conversation_exported",
    "meto_conversation_searched",
    "meto_conversation_deleted",
}
```

---

## 3. Conversation Metrics

### 3.1 Core Conversation KPIs

```python
# Computed per session
class ConversationMetrics:
    
    # Volume
    messages_per_session: float              # Average messages exchanged
    user_messages_count: int                 # User turns
    meto_messages_count: int                 # Meto turns
    
    # Duration
    session_duration_seconds: int            # Time from open to close
    time_to_first_message_seconds: int       # Time from open to first user message
    time_to_first_response_seconds: float    # Time from send to first chunk (TTFT)
    
    # Completion
    session_completion_rate: float           # Sessions where user got a response / total
    abandon_rate: float                      # Sessions closed before any message
    mid_session_abandon_rate: float          # Sessions closed after ≥1 message but incomplete
    
    # Engagement
    follow_up_question_rate: float           # % sessions with ≥3 turns
    tool_usage_per_session: float            # Average tool calls per session
    conversation_return_rate: float          # % users returning to chat within 24h
```

### 3.2 Event Schema

```python
# meto_session_completed event
@dataclass
class SessionCompletedEvent(BaseEvent):
    event_name: str = "meto_session_completed"
    
    # Session data
    turn_count: int
    duration_seconds: int
    
    # Resolution
    completion_type: str        # "natural" | "timeout" | "user_close" | "error"
    had_tool_usage: bool
    had_escalation: bool
    had_safety_flag: bool
    had_fallback: bool
    
    # Token usage (aggregated for session)
    total_tokens_input: int
    total_tokens_output: int
    
    # Provider used (most common in session)
    primary_provider: str       # "claude" | "openai"
    fallback_occurred: bool
```

---

## 4. Feature Usage Analytics

### 4.1 Quick Prompts

```python
# meto_quickprompt_shown event
@dataclass
class QuickPromptShownEvent(BaseEvent):
    event_name: str = "meto_quickprompt_shown"
    
    prompts_displayed: list[str]     # Prompt text slugs (NOT full text — hashed)
    prompt_count: int
    screen_id: str                   # Which screen generated these prompts

# meto_quickprompt_tapped event
@dataclass
class QuickPromptTappedEvent(BaseEvent):
    event_name: str = "meto_quickprompt_tapped"
    
    prompt_slug: str                 # Which prompt was tapped
    prompt_position: int             # 0-indexed position in list
    time_to_tap_seconds: float       # Time from shown to tap
    total_prompts_shown: int
```

**Quick Prompt Analytics Computations:**
```sql
-- CTR per prompt slug
SELECT 
    prompt_slug,
    COUNT(CASE WHEN event_name = 'meto_quickprompt_tapped' THEN 1 END) as taps,
    COUNT(CASE WHEN event_name = 'meto_quickprompt_shown' THEN 1 END) as shows,
    ROUND(100.0 * taps / NULLIF(shows, 0), 1) as ctr_percent
FROM meto_events
WHERE event_name IN ('meto_quickprompt_tapped', 'meto_quickprompt_shown')
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY prompt_slug
ORDER BY ctr_percent DESC;

-- Drop-off rate after quick prompt tap
-- (Did user ask a follow-up or close immediately?)
SELECT
    prompt_slug,
    COUNT(*) as total_taps,
    COUNT(CASE WHEN follow_up_turns >= 2 THEN 1 END) as engaged,
    ROUND(100.0 * COUNT(CASE WHEN follow_up_turns >= 2 THEN 1 END) / COUNT(*), 1) as engagement_rate
FROM (
    SELECT 
        qp.prompt_slug,
        COUNT(msg.id) as follow_up_turns
    FROM meto_events qp
    LEFT JOIN messages msg ON msg.session_id = qp.session_id AND msg.turn_index > 1
    WHERE qp.event_name = 'meto_quickprompt_tapped'
    GROUP BY qp.session_id, qp.prompt_slug
) sub
GROUP BY prompt_slug;
```

### 4.2 Tool Usage Metrics

```python
@dataclass
class ToolExecutedEvent(BaseEvent):
    event_name: str = "meto_tool_executed"
    
    tool_name: str                  # Which tool
    tool_version: str               # Tool version
    
    execution_status: str           # "success" | "failed" | "rate_limited"
    execution_duration_ms: int
    
    required_confirmation: bool
    user_confirmed: bool            # If required_confirmation
    
    # NO sensitive data — no tool arguments or results
```

**Tool Usage Dashboard:**
```sql
-- Tool usage breakdown (last 30 days)
SELECT 
    tool_name,
    COUNT(*) as total_calls,
    SUM(CASE WHEN execution_status = 'success' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN execution_status = 'failed' THEN 1 ELSE 0 END) as failures,
    AVG(execution_duration_ms) as avg_duration_ms,
    SUM(CASE WHEN required_confirmation AND NOT user_confirmed THEN 1 ELSE 0 END) as user_cancelled
FROM meto_events
WHERE event_name = 'meto_tool_executed'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY tool_name
ORDER BY total_calls DESC;
```

### 4.3 Memory Opt-in Rate

```sql
-- Memory opt-in rate by category
SELECT
    memory_category,
    SUM(CASE WHEN event_name = 'meto_memory_optin' THEN 1 ELSE 0 END) as optins,
    SUM(CASE WHEN event_name = 'meto_memory_optout' THEN 1 ELSE 0 END) as optouts,
    ROUND(100.0 * SUM(CASE WHEN event_name = 'meto_memory_optin' THEN 1 ELSE 0 END) / 
          NULLIF(SUM(CASE WHEN event_name IN ('meto_memory_optin', 'meto_memory_optout') THEN 1 ELSE 0 END), 0), 1) as optin_rate
FROM meto_events
WHERE event_name IN ('meto_memory_optin', 'meto_memory_optout')
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY memory_category;
```

---

## 5. Fallback Analytics

### 5.1 Fallback Event

```python
@dataclass
class ProviderFallbackEvent(BaseEvent):
    event_name: str = "meto_provider_fallback"
    
    primary_provider: str           # "claude"
    fallback_provider: str          # "openai"
    
    fallback_reason: str            # "timeout" | "rate_limit" | "server_error" | "context_too_long"
    error_code: str                 # Provider error code
    
    # Timing
    primary_attempt_duration_ms: int    # How long we waited before fallback
    fallback_duration_ms: int           # How long fallback took
    total_request_duration_ms: int
    
    # Was fallback successful?
    fallback_success: bool
```

### 5.2 Fallback Dashboard

```sql
-- Fallback rate by hour (last 24h)
SELECT
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as total_requests,
    SUM(CASE WHEN event_name = 'meto_provider_fallback' THEN 1 ELSE 0 END) as fallbacks,
    ROUND(100.0 * SUM(CASE WHEN event_name = 'meto_provider_fallback' THEN 1 ELSE 0 END) / 
          NULLIF(COUNT(*), 0), 2) as fallback_rate_percent
FROM meto_events
WHERE timestamp > NOW() - INTERVAL '24 hours'
  AND event_name IN ('meto_response_received', 'meto_provider_fallback')
GROUP BY hour
ORDER BY hour;

-- Fallback reasons breakdown
SELECT
    fallback_reason,
    COUNT(*) as count,
    AVG(total_request_duration_ms) as avg_total_duration_ms,
    SUM(CASE WHEN fallback_success THEN 1 ELSE 0 END) as successful_fallbacks
FROM meto_events
WHERE event_name = 'meto_provider_fallback'
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY fallback_reason
ORDER BY count DESC;
```

---

## 6. Latency Metrics

### 6.1 Core Latency Events

```python
@dataclass
class ResponseReceivedEvent(BaseEvent):
    event_name: str = "meto_response_received"
    
    provider: str                           # "claude" | "openai"
    is_fallback: bool
    
    # Latency breakdown
    context_assembly_ms: int                # Time to assemble context
    memory_retrieval_ms: int                # Time to get memories
    prompt_build_ms: int                    # Time to build prompt
    time_to_first_token_ms: int            # TTFT — most important for UX
    time_to_last_token_ms: int             # Total streaming duration
    total_request_ms: int                   # End-to-end
    
    # Token counts
    input_tokens: int
    output_tokens: int
```

### 6.2 Latency Dashboard

```sql
-- P50/P95/P99 latency by provider (last 24h)
SELECT
    provider,
    COUNT(*) as requests,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY time_to_first_token_ms) as p50_ttft_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY time_to_first_token_ms) as p95_ttft_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY time_to_first_token_ms) as p99_ttft_ms,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_request_ms) as p50_total_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_request_ms) as p95_total_ms,
    AVG(total_request_ms) as avg_total_ms
FROM meto_events
WHERE event_name = 'meto_response_received'
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY provider;

-- Latency trend (hourly, last 7 days)
SELECT
    DATE_TRUNC('hour', timestamp) as hour,
    provider,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY time_to_first_token_ms) as p95_ttft,
    AVG(time_to_first_token_ms) as avg_ttft
FROM meto_events
WHERE event_name = 'meto_response_received'
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY hour, provider
ORDER BY hour, provider;
```

---

## 7. Token Usage & Cost

### 7.1 Token Metrics

```sql
-- Daily token usage breakdown
SELECT
    DATE_TRUNC('day', timestamp) as day,
    provider,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    AVG(input_tokens) as avg_input_per_request,
    AVG(output_tokens) as avg_output_per_request,
    COUNT(*) as total_requests,
    
    -- Cost estimation (update rates when provider pricing changes)
    SUM(input_tokens) * 0.000003 as estimated_input_cost_usd,    -- Claude Sonnet 4.5 rate
    SUM(output_tokens) * 0.000015 as estimated_output_cost_usd
FROM meto_events
WHERE event_name = 'meto_response_received'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY day, provider
ORDER BY day DESC;

-- Token breakdown by context block type
-- (Requires additional event fields for context breakdown)
SELECT
    DATE_TRUNC('week', timestamp) as week,
    AVG(context_block_tokens) as avg_context_tokens,
    AVG(history_tokens) as avg_history_tokens,
    AVG(memory_tokens) as avg_memory_tokens,
    AVG(system_tokens) as avg_system_tokens,
    AVG(output_tokens) as avg_output_tokens
FROM meto_events
WHERE event_name = 'meto_response_received'
GROUP BY week
ORDER BY week DESC;
```

---

## 8. Provider Usage & Performance

```sql
-- Provider split and success rate
SELECT
    provider,
    COUNT(*) as total_requests,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as share_percent,
    SUM(CASE WHEN execution_status = 'success' THEN 1 ELSE 0 END) as successes,
    ROUND(100.0 * SUM(CASE WHEN execution_status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM meto_provider_stats  -- Materialized view
WHERE period > NOW() - INTERVAL '30 days'
GROUP BY provider;
```

---

## 9. Error Analytics

### 9.1 Error Event

```python
@dataclass
class ProviderErrorEvent(BaseEvent):
    event_name: str = "meto_provider_error"
    
    provider: str
    error_type: str             # "timeout" | "rate_limit" | "server_error" | "context_too_long" | "content_filter"
    error_code: str             # Provider-specific code
    http_status: int
    
    was_retried: bool
    retry_count: int
    was_shown_to_user: bool     # Or was it silently handled?
    
    # Context (no sensitive data)
    request_type: str           # "chat" | "tool" | "summary"
```

### 9.2 Error Dashboard

```sql
-- Error rate by type (last 7 days)
SELECT
    error_type,
    provider,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct_of_errors,
    SUM(CASE WHEN was_shown_to_user THEN 1 ELSE 0 END) as user_visible_errors,
    AVG(retry_count) as avg_retries
FROM meto_events
WHERE event_name = 'meto_provider_error'
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY error_type, provider
ORDER BY count DESC;

-- Error rate over time
SELECT
    DATE_TRUNC('hour', timestamp) as hour,
    total_requests.cnt as total_requests,
    errors.cnt as errors,
    ROUND(100.0 * errors.cnt / NULLIF(total_requests.cnt, 0), 2) as error_rate_pct
FROM (
    SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(*) as cnt
    FROM meto_events WHERE event_name = 'meto_response_received'
      AND timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY hour
) total_requests
LEFT JOIN (
    SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(*) as cnt
    FROM meto_events WHERE event_name = 'meto_provider_error'
      AND timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY hour
) errors ON errors.hour = total_requests.hour
ORDER BY hour;
```

---

## 10. User Satisfaction

### 10.1 Explicit Feedback

```python
@dataclass
class FeedbackEvent(BaseEvent):
    event_name: str = "meto_feedback_thumbsup" | "meto_feedback_thumbsdown"
    
    message_id: str             # Which Meto message was rated
    screen_id: str              # Context screen
    topic_category: str         # Inferred topic (labs/meds/metrics/nutrition/general)
    
    # For thumbsdown only
    feedback_reason: str | None  # "incorrect" | "unhelpful" | "inappropriate" | "other"
    has_comment: bool

@dataclass
class FeedbackCommentEvent(BaseEvent):
    event_name: str = "meto_feedback_comment_submitted"
    
    sentiment: str              # "positive" | "negative" | "neutral" (inferred, not from NLP of content)
    # NO actual comment text in events for privacy
    word_count: int             # Approximate length only
```

### 10.2 Implicit Signals

```python
# Derived from conversation patterns — no additional events needed

IMPLICIT_POSITIVE_SIGNALS = [
    "follow_up_question_in_same_session",     # User asked more → engaged
    "tool_action_confirmed",                   # User took action Meto suggested
    "session_duration > 5 minutes",            # Extended engagement
    "returned within 24h",                     # Retention signal
    "quick_prompt_tapped_then_followed_up",   # Deep engagement with prompts
]

IMPLICIT_NEGATIVE_SIGNALS = [
    "session_abandoned_after_first_response",  # Got response, left
    "response_cancelled_mid_stream",           # Didn't want to see response
    "repeated_same_question",                  # Meto didn't answer well
    "thumbsdown",                              # Explicit
    "session_duration < 30 seconds",           # No real interaction
]
```

### 10.3 CSAT Dashboard

```sql
-- CSAT score (thumbs up / total rated)
SELECT
    DATE_TRUNC('week', timestamp) as week,
    SUM(CASE WHEN event_name = 'meto_feedback_thumbsup' THEN 1 ELSE 0 END) as thumbsup,
    SUM(CASE WHEN event_name = 'meto_feedback_thumbsdown' THEN 1 ELSE 0 END) as thumbsdown,
    ROUND(100.0 * SUM(CASE WHEN event_name = 'meto_feedback_thumbsup' THEN 1 ELSE 0 END) / 
          NULLIF(COUNT(CASE WHEN event_name IN ('meto_feedback_thumbsup', 'meto_feedback_thumbsdown') THEN 1 END), 0), 1) as csat_pct
FROM meto_events
WHERE event_name IN ('meto_feedback_thumbsup', 'meto_feedback_thumbsdown')
  AND timestamp > NOW() - INTERVAL '90 days'
GROUP BY week
ORDER BY week DESC;
```

---

## 11. Retention Metrics

```sql
-- DAU / WAU / MAU for Meto specifically
-- (Users who had ≥1 Meto conversation that day/week/month)

-- DAU
SELECT
    DATE_TRUNC('day', timestamp) as day,
    COUNT(DISTINCT user_cohort_id) as dau_meto
FROM meto_events
WHERE event_name = 'meto_chat_opened'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day;

-- Meto retention vs App retention
-- Cohort: users who started Meto in week W
-- Retention: % still using Meto in week W+1, W+2, W+4
SELECT
    cohort_week,
    COUNT(DISTINCT user_cohort_id) as cohort_size,
    COUNT(DISTINCT CASE WHEN week_offset = 1 THEN user_cohort_id END) as w1_retained,
    COUNT(DISTINCT CASE WHEN week_offset = 2 THEN user_cohort_id END) as w2_retained,
    COUNT(DISTINCT CASE WHEN week_offset = 4 THEN user_cohort_id END) as w4_retained
FROM meto_retention_cohorts  -- Pre-computed
GROUP BY cohort_week
ORDER BY cohort_week DESC;
```

---

## 12. Conversion Funnels

### 12.1 Core Meto Funnel

```
Floating button visible
        │ (auto: user opens the screen)
        ▼
Floating button tapped
        │ CTR_1 = taps / visible
        ▼
Chat opened (first message screen shown)
        │ CTR_2 = opened / taps
        ▼
First message sent
        │ CTR_3 = sent / opened
        ▼
Response received
        │ (completion = received / sent)
        ▼
Follow-up message sent (turn >= 2)
        │ ENGAGEMENT_RATE = followup / received
        ▼
Tool action executed
        │ TOOL_RATE = tool_use / session
        ▼
Session completed (natural close)
        │ COMPLETION_RATE = completed / (completed + abandoned)
```

### 12.2 Funnel Analytics

```sql
-- Meto funnel (last 30 days)
SELECT
    COUNT(DISTINCT CASE WHEN event_name = 'meto_chat_opened' THEN session_id END) as step_1_opened,
    COUNT(DISTINCT CASE WHEN event_name = 'meto_message_sent' AND turn_index = 1 THEN session_id END) as step_2_first_message,
    COUNT(DISTINCT CASE WHEN event_name = 'meto_response_received' AND turn_index = 1 THEN session_id END) as step_3_first_response,
    COUNT(DISTINCT CASE WHEN event_name = 'meto_message_sent' AND turn_index = 2 THEN session_id END) as step_4_followup,
    COUNT(DISTINCT CASE WHEN event_name = 'meto_tool_executed' AND execution_status = 'success' THEN session_id END) as step_5_tool_used,
    COUNT(DISTINCT CASE WHEN event_name = 'meto_session_completed' AND completion_type = 'natural' THEN session_id END) as step_6_completed
FROM meto_events
WHERE timestamp > NOW() - INTERVAL '30 days';
```

---

## 13. Cohort Analysis

```sql
-- Behavior comparison: new vs returning users
SELECT
    is_new_user,
    COUNT(DISTINCT session_id) as total_sessions,
    AVG(turn_count) as avg_turns,
    AVG(duration_seconds) / 60.0 as avg_duration_minutes,
    ROUND(100.0 * SUM(CASE WHEN had_tool_usage THEN 1 ELSE 0 END) / COUNT(*), 1) as tool_usage_rate,
    ROUND(100.0 * SUM(CASE WHEN completion_type = 'natural' THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_rate
FROM meto_session_stats
WHERE period > NOW() - INTERVAL '30 days'
GROUP BY is_new_user;

-- Segmentation by health condition
SELECT
    user_health_segment,
    COUNT(DISTINCT user_cohort_id) as users,
    AVG(sessions_per_user) as avg_sessions,
    AVG(messages_per_session) as avg_messages,
    AVG(csat_score) as avg_csat
FROM meto_user_segments
WHERE period > NOW() - INTERVAL '30 days'
GROUP BY user_health_segment;
```

---

## 14. Medical Topic Distribution

### 14.1 Topic Classifier

```python
# Topic classification từ screen context + quick prompt category
# KHÔNG dùng NLP trên conversation content (privacy)
# Dùng screen_id + entity_type + tool_name để infer topic

TOPIC_INFERENCE_RULES = {
    "labs":                "lab_interpretation",
    "medications":         "medication_info",
    "metrics":             "health_metrics",
    "nutrition":           "nutrition_advice",
    "care_plan":           "care_plan_management",
    "dashboard":           "general_health",
    
    # From tool usage
    "tool:explain_lab":            "lab_interpretation",
    "tool:explain_medication":     "medication_info",
    "tool:record_metric":          "health_metrics",
    "tool:nutrition_recommendation": "nutrition_advice",
    "tool:symptom_intake":         "symptom_assessment",
    "tool:create_reminder":        "care_management",
}
```

### 14.2 Topic Distribution Dashboard

```sql
-- Topic breakdown (last 30 days)
SELECT
    inferred_topic,
    COUNT(*) as session_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct,
    AVG(turn_count) as avg_turns,
    AVG(csat_score) as avg_csat
FROM meto_session_topics
WHERE period > NOW() - INTERVAL '30 days'
GROUP BY inferred_topic
ORDER BY session_count DESC;
```

---

## 15. A/B Testing Framework

### 15.1 Experiment Design

```python
@dataclass
class MetoExperiment:
    experiment_id: str
    name: str
    description: str
    
    # Assignment
    traffic_allocation: float           # 0.0 - 1.0 (fraction of eligible users)
    control_variant: str = "control"
    treatment_variants: list[str]       # Can be multiple variants
    
    # Eligibility
    eligible_user_segments: list[str]   # Which health segments to include
    exclude_new_users: bool = False     # Exclude first 7 days
    
    # Primary metric (for statistical test)
    primary_metric: str                 # "session_completion_rate" | "csat_score" | ...
    minimum_detectable_effect: float    # 0.05 = 5% lift
    
    # Duration
    min_runtime_days: int = 14
    max_runtime_days: int = 42
    
    # Status
    status: str                         # "draft" | "running" | "stopped" | "graduated"
    start_date: datetime | None
    end_date: datetime | None
    
    # Results
    winning_variant: str | None = None
    graduation_date: datetime | None = None
```

### 15.2 Experiment Assignment

```python
def assign_experiment_variant(
    user_cohort_id: str,
    experiment: MetoExperiment
) -> str:
    """
    Deterministic assignment: same user always gets same variant.
    Uses hash of user_cohort_id + experiment_id for stability.
    """
    hash_input = f"{user_cohort_id}:{experiment.experiment_id}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    bucket = (hash_value % 1000) / 1000.0  # 0.0 - 1.0
    
    if bucket >= experiment.traffic_allocation:
        return "control"  # Not in experiment
    
    # Assign to variant
    variant_bucket = (bucket / experiment.traffic_allocation) * len(experiment.treatment_variants)
    variant_index = int(variant_bucket)
    return experiment.treatment_variants[min(variant_index, len(experiment.treatment_variants) - 1)]
```

### 15.3 Graduation Criteria

```
An experiment can graduate (winner shipped) when:

1. Statistical significance: p-value < 0.05 (two-tailed)
2. Minimum sample size: 500 users per variant
3. Minimum runtime: 14 days (to capture weekly patterns)
4. Primary metric lift: >= MDE (minimum detectable effect)
5. No safety regressions: escalation_rate, error_rate within bounds
6. CSAT score: not significantly lower than control

Gate checks (automated daily):
- [ ] Sample size met
- [ ] Runtime met  
- [ ] Statistical significance reached
- [ ] No safety alerts triggered
- [ ] Secondary metrics: no significant regressions

Manual review required before graduation:
- [ ] PM review of results
- [ ] Medical safety review (if feature touches clinical content)
- [ ] QA sign-off
```

---

## 16. Privacy Requirements

### 16.1 Data Minimization

```python
ANALYTICS_PRIVACY_RULES = {
    # Data that MUST NOT appear in events
    "forbidden_fields": [
        "user_id",              # Use user_cohort_id (hashed)
        "user_name",
        "health_values",        # No actual lab values, blood pressure, etc.
        "medication_names",     # No actual medication names
        "conversation_content", # No messages
        "symptom_descriptions", # No actual symptoms
        "location",             # No location data
        "device_id",            # No hardware identifiers
        "ip_address",           # No IP
    ],
    
    # Allowed demographic dimensions
    "allowed_dimensions": [
        "user_cohort_id",       # Hashed, not reversible
        "user_age_bracket",     # "36-45" — not exact age
        "user_gender_segment",  # "male" / "female" / "other" / "unknown"
        "user_health_segment",  # Broad category only
        "is_new_user",          # Boolean
        "platform",             # "ios" / "android" / "web"
        "app_version",
    ]
}
```

### 16.2 Retention & Deletion

```python
ANALYTICS_RETENTION = {
    "raw_events":           "90_days",      # After 90 days → aggregate only
    "aggregated_metrics":   "2_years",      # Keep aggregates longer
    "experiment_data":      "3_years",      # For reproducibility
    "cohort_analysis":      "2_years",
    
    # On user deletion request:
    # - anonymize user_cohort_id in all events (replace with "deleted_user")
    # - This preserves aggregate counts while removing individual tracking
    "user_deletion_handling": "anonymize"   # Not hard delete (would break aggregates)
}
```

### 16.3 User Transparency

Events collected are disclosed in Privacy Policy:
- Section: "Meto AI Analytics"
- Lists: event categories, what's collected, what's NOT collected
- Opt-out: Meto analytics can be disabled in Settings → Privacy → Analytics

---

## 17. Dashboard Design

### 17.1 Operational Dashboard (Grafana — Real-time)

**Panels:**
1. **Health Overview** (top row)
   - Current error rate (gauge, red >2%)
   - Current fallback rate (gauge, yellow >5%)
   - P95 TTFT last hour (gauge, red >5s)
   - Active sessions now (number)

2. **Request Volume** (time series, last 24h)
   - Requests per minute
   - Error rate overlay
   - Fallback rate overlay

3. **Latency** (time series, last 24h)
   - P50/P95/P99 TTFT by provider
   - P50/P95 total request duration

4. **Provider Split** (pie chart)
   - Claude vs OpenAI requests last hour

5. **Error Breakdown** (bar chart)
   - Error types last 24h

6. **Token Usage** (time series)
   - Input/output tokens per hour
   - Cost estimate

### 17.2 Product Dashboard (Weekly)

**KPI Cards (top):**
- WAU Meto (users with ≥1 session)
- Session Completion Rate
- CSAT Score
- P95 TTFT

**Trends (time series, last 90 days):**
- DAU / WAU / MAU
- Session count per day
- Average messages per session

**Feature Breakdown:**
- Quick prompt CTR by screen
- Tool usage by tool name
- Topic distribution donut

**Funnel:**
- Conversion funnel visualization
- Drop-off % at each step

**Retention:**
- D1, D7, D30 retention cohort chart
- Meto retention vs overall app retention

### 17.3 Executive Dashboard (Monthly)

- Monthly active Meto users
- Month-over-month growth
- CSAT trend
- Key experiments graduated
- Top user issues (from thumbsdown reasons)
- Provider cost breakdown

---

## 18. KPI Definitions

### 18.1 Primary KPIs

| KPI | Definition | Target | Current |
|-----|-----------|--------|---------|
| **WAU Meto** | Unique users with ≥1 session per week | >40% of active app users | TBD at launch |
| **Session Completion Rate** | Sessions where user received ≥1 response / total opened | >85% | TBD |
| **CSAT Score** | Thumbs up / (thumbs up + thumbs down) | >80% | TBD |
| **P95 TTFT** | 95th percentile Time-to-First-Token | <3,000ms | TBD |
| **Meto Retention D7** | % users still using Meto 7 days after first use | >50% | TBD |

### 18.2 Secondary KPIs

| KPI | Definition | Target |
|-----|-----------|--------|
| Average messages per session | Mean turn count | >3 turns |
| Tool action rate | Sessions with ≥1 tool execution / total | >15% |
| Quick prompt CTR | Taps / prompts shown | >20% |
| Fallback rate | Fallback events / total requests | <5% |
| Error rate | Errors / total requests | <1% |
| Memory opt-in rate | Users with memory enabled / total | >60% |
| Conversation return rate | % users returning to chat within 24h | >30% |

---

## 19. Alert Thresholds

```python
ALERT_RULES = [
    AlertRule(
        name="High Error Rate",
        query="error_rate > 0.02",  # >2%
        window="5 minutes",
        severity="CRITICAL",
        notify=["oncall-engineer", "tech-lead"],
        description="Meto error rate exceeded 2%. Immediate investigation required."
    ),
    AlertRule(
        name="High Fallback Rate",
        query="fallback_rate > 0.10",  # >10%
        window="10 minutes",
        severity="WARNING",
        notify=["oncall-engineer"],
        description="Fallback to OpenAI rate exceeded 10%. Check Claude API status."
    ),
    AlertRule(
        name="P95 Latency Spike",
        query="p95_ttft_ms > 5000",  # >5 seconds
        window="10 minutes",
        severity="WARNING",
        notify=["oncall-engineer"],
        description="P95 TTFT exceeded 5 seconds. User experience degraded."
    ),
    AlertRule(
        name="Session Completion Rate Drop",
        query="session_completion_rate < 0.70",  # <70%
        window="1 hour",
        severity="WARNING",
        notify=["tech-lead", "pm"],
        description="Session completion rate dropped below 70%. Possible UX issue."
    ),
    AlertRule(
        name="Safety Escalation Spike",
        query="escalation_rate > escalation_rate_1d_avg * 3",  # 3x normal
        window="30 minutes",
        severity="HIGH",
        notify=["tech-lead", "medical-safety-lead"],
        description="Safety escalations spiked 3x above normal. Investigate immediately."
    ),
    AlertRule(
        name="Zero Requests",
        query="request_count < 1",  # No traffic at all
        window="15 minutes",
        severity="CRITICAL",
        notify=["oncall-engineer"],
        description="No Meto requests in 15 minutes. Service may be down."
    ),
]
```

---

*Xem thêm: 04_SAFETY_PRIVACY.md (audit logging vs analytics separation), 08_CONVERSATION_ENGINE.md (session events), 09_TOOLS_AND_ACTIONS.md (tool events)*
