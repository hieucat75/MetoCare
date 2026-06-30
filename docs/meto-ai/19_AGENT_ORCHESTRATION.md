# Meto AI — Agent Orchestration Layer

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Agent Orchestration Layer (AOL) là tầng điều phối trung tâm của Meto — chuyển đổi Meto từ một AI chatbot thành một **Agentic AI** thực thụ. AOL nhận user intent, lập kế hoạch thực thi, chọn công cụ, thực thi an toàn, và tổng hợp kết quả thành phản hồi cá nhân hóa.

**Mục tiêu kiến trúc:** Meto như một AI Health Operating System, không phải chatbot.

**File backend:**
- `app/ai/agent/` — Agent core modules
- `app/ai/agent/planner.py` — Intent → execution plan
- `app/ai/agent/reasoner.py` — Multi-step reasoning
- `app/ai/agent/context_builder.py` — Context assembly
- `app/ai/agent/retriever.py` — Knowledge & memory retrieval
- `app/ai/agent/tool_selector.py` — Tool selection & permission check
- `app/ai/agent/action_validator.py` — Pre-execution validation
- `app/ai/agent/safety_guard.py` — Safety pre/post check
- `app/ai/agent/response_composer.py` — Response formatting
- `app/ai/agent/state_manager.py` — Agent state management
- `app/ai/agent/fallback_manager.py` — Degradation handling
- `app/ai/agent/error_recovery.py` — Retry & partial failure

---

## 1. Platform Layer View — AI Health Operating System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Chat UI / Voice UI                               │
│           (Next.js frontend, Meto Aura mascot, streaming)          │
├─────────────────────────────────────────────────────────────────────┤
│              Agent Orchestration Layer                              │
│  Planner | Reasoner | Tool Selector | Safety Guard                 │
│  Context Builder | Memory Resolver | Action Validator              │
│  State Manager | Fallback Manager | Error Recovery                  │
├──────────────┬──────────────┬────────────────────────────────────────┤
│ Context      │ Memory       │ Knowledge                            │
│ Engine       │ Engine       │ Layer                                │
│ (9 blocks)   │ (3 tiers)    │ (4-tier KB)                         │
├──────────────┴──────────────┴────────────────────────────────────────┤
│           Clinical Reasoning Layer                                  │
│    Observation → Interpretation → Recommendation                    │
│    (14_CLINICAL_REASONING.md)                                       │
├─────────────────────────────────────────────────────────────────────┤
│           Recommendation Engine                                    │
│    12 categories, priority queue, deduplication, feedback loop     │
│    (15_RECOMMENDATION_ENGINE.md)                                    │
├─────────────────────────────────────────────────────────────────────┤
│    Tool Engine    │  Doctor Handoff │  Multimodal                  │
│  (12 tools)       │  (4-tier escalate│  (OCR|Vision|Voice)        │
│  (09_TOOLS)       │  17_HANDOFF)     │  (18_MULTIMODAL)           │
├─────────────────────────────────────────────────────────────────────┤
│         Conversation Engine (session/state/streaming)               │
│                    (08_CONVERSATION_ENGINE.md)                      │
├─────────────────────────────────────────────────────────────────────┤
│              Provider Abstraction Layer                             │
│  Claude | OpenAI | Gemini | Local | Future                        │
│                    (20_PROVIDER_ABSTRACTION.md)                     │
├─────────────────────────────────────────────────────────────────────┤
│    Safety Layer  │  Analytics Layer │ Audit Layer                  │
│  (04_SAFETY)     │  (metrics emit)  │ (full audit trail)          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent Components — Chi tiết

### 2.1 Planner

```python
class AgentPlanner:
    """
    Nhận user intent → tạo ExecutionPlan.
    Plan gồm ordered steps, mỗi step có tool hoặc reasoning call,
    kèm expected output và fallback nếu step thất bại.
    """

    async def plan(
        self,
        user_message: str,
        context: AssembledContext,
        memory: list[MemoryItem],
        session_state: SessionState
    ) -> ExecutionPlan:

        # Step 1: Classify intent
        intent = await self._classify_intent(user_message, context)

        # Step 2: Decide planning mode
        if intent.is_simple_query:
            return self._simple_plan(intent)

        if intent.requires_tool_use:
            return await self._tool_use_plan(intent, context)

        if intent.requires_clinical_reasoning:
            return await self._clinical_plan(intent, context)

        return await self._general_plan(intent, context)

    async def _classify_intent(
        self,
        message: str,
        context: AssembledContext
    ) -> Intent:
        """
        Intent categories:
        - EXPLAIN_LAB: "HbA1c của tôi 7.8% nghĩa là gì?"
        - EXPLAIN_MEDICATION: "Metformin dùng để làm gì?"
        - EXPLAIN_METRIC: "Huyết áp 145/90 có cao không?"
        - CREATE_REMINDER: "Nhắc tôi uống thuốc lúc 8 giờ"
        - RECORD_DATA: "Vừa đo được 135 mg/dL"
        - PREPARE_APPOINTMENT: "Chuẩn bị câu hỏi cho bác sĩ"
        - ASK_SYMPTOM: "Tôi đang bị đau đầu"
        - CARE_PLAN_HELP: "Hôm nay tôi cần làm gì?"
        - GENERAL_HEALTH_QA: "Tiểu đường có nguy hiểm không?"
        - OUT_OF_SCOPE: "Cho tôi biết giá cổ phiếu"
        - EMERGENCY_INDICATOR: (triggers DHE immediately)
        """
        return await self.llm_mini.classify(
            message=message,
            context_summary=context.to_brief_summary(),
            categories=INTENT_CATEGORIES
        )

@dataclass
class ExecutionPlan:
    intent: Intent
    steps: list[PlanStep]
    estimated_tools: list[str]
    requires_clinical_reasoning: bool
    requires_recommendation_engine: bool
    requires_doctor_handoff_check: bool
    fallback_plan: ExecutionPlan | None    # Simpler plan if primary fails
    max_execution_time_ms: int = 5000

@dataclass
class PlanStep:
    step_id: int
    action: str                        # "call_tool" | "reason" | "retrieve" | "compose"
    tool_name: str | None              # If action = "call_tool"
    tool_args: dict | None
    depends_on: list[int]              # Step IDs this depends on
    fallback: str | None               # What to do if step fails
    is_optional: bool = False
```

### 2.2 Reasoner

```python
class AgentReasoner:
    """
    Multi-step reasoning với chain-of-thought và self-critique.
    Chỉ dùng cho complex queries — không phải mọi request.
    """

    REASONING_TRIGGER_THRESHOLD = 0.7  # Confidence khi cần full reasoning

    async def reason(
        self,
        query: str,
        context: AssembledContext,
        knowledge_chunks: list[KnowledgeChunk],
        memory: list[MemoryItem],
        previous_steps: list[StepResult]
    ) -> ReasoningResult:

        # Chain-of-thought reasoning
        chain = await self.llm.reason_with_chain_of_thought(
            query=query,
            context=context.to_prompt_block(),
            knowledge=self._format_knowledge(knowledge_chunks),
            memory=self._format_memory(memory),
            previous_steps=previous_steps,
            safety_constraints=REASONING_SAFETY_CONSTRAINTS
        )

        # Self-critique pass
        critique = await self._self_critique(chain.reasoning, chain.conclusion)

        # If critique identifies issues → revise
        if critique.has_issues:
            revised = await self._revise_reasoning(chain, critique)
            return ReasoningResult(
                conclusion=revised.conclusion,
                chain_of_thought=revised.chain,
                critique=critique,
                confidence=revised.confidence,
                was_revised=True
            )

        return ReasoningResult(
            conclusion=chain.conclusion,
            chain_of_thought=chain.reasoning,
            confidence=chain.confidence,
            was_revised=False
        )

    async def _self_critique(
        self,
        reasoning: str,
        conclusion: str
    ) -> CritiqueResult:
        """
        Meto checks its own reasoning for:
        - Diagnosis claims → reject
        - Prescription suggestions → reject
        - Overconfident claims → flag
        - Unsupported conclusions → flag
        """
        issues = []
        for pattern in FORBIDDEN_REASONING_PATTERNS:
            if re.search(pattern, conclusion, re.IGNORECASE):
                issues.append(ReasoningIssue(
                    type="scope_violation",
                    pattern=pattern,
                    severity="CRITICAL"
                ))

        return CritiqueResult(
            has_issues=len(issues) > 0,
            issues=issues,
            revision_needed=any(i.severity == "CRITICAL" for i in issues)
        )

REASONING_SAFETY_CONSTRAINTS = """
Khi suy luận, tuân thủ nghiêm ngặt:
1. Không kết luận chẩn đoán bệnh lý
2. Không đề xuất thay đổi thuốc
3. Không khẳng định kết luận lâm sàng — chỉ nêu khả năng
4. Mọi kết luận phải có cơ sở từ dữ liệu trong context
5. Khi không chắc → thừa nhận không chắc
"""
```

### 2.3 Context Builder

```python
class AgentContextBuilder:
    """
    Assembly 9 context blocks + memory + knowledge cho agent execution.
    Quản lý token budget tổng thể.
    """

    TOTAL_TOKEN_BUDGET = 12000
    BUDGET_ALLOCATION = {
        "system_prompt": 1500,
        "context_blocks": 2000,        # 9 blocks (see 02_CONTEXT_ENGINE.md)
        "memory": 500,
        "knowledge": 1000,
        "conversation_history": 4000,
        "tool_schemas": 500,
        "response_buffer": 2500,
    }

    async def build(
        self,
        user_id: str,
        screen_id: str,
        user_message: str,
        session: ConversationSession,
        intent: Intent
    ) -> AssembledContext:

        # Parallel assembly
        results = await asyncio.gather(
            self.context_engine.assemble(user_id, screen_id),
            self.memory_engine.get_top_k_memories(user_id, query=user_message),
            self.knowledge_resolver.retrieve_for_intent(intent, max_tokens=1000),
            self.tool_selector.get_available_schemas(screen_id),
        )

        context_blocks, memories, knowledge, tool_schemas = results

        # Fit within token budget
        fitted = self._fit_within_budget(
            context_blocks=context_blocks,
            memories=memories,
            knowledge=knowledge,
            tool_schemas=tool_schemas,
            history=session.get_recent_messages(max_tokens=4000)
        )

        return AssembledContext(**fitted)

    def _fit_within_budget(self, **components) -> dict:
        """
        Priority order khi budget tight:
        1. System prompt (non-negotiable)
        2. Safety flags (non-negotiable)
        3. User profile + health summary (almost always)
        4. Screen context (always)
        5. Recent conversation (last 5 turns minimum)
        6. Memory (top 3 if budget allows)
        7. Knowledge (reduced if needed)
        8. Older conversation (compress if needed)
        9. Tool schemas (drop optional tools)
        """
        budget = self.TOTAL_TOKEN_BUDGET
        fitted = {}

        for priority_item in PRIORITY_ORDER:
            item_tokens = self._estimate_tokens(components[priority_item])
            if budget - item_tokens > 0:
                fitted[priority_item] = components[priority_item]
                budget -= item_tokens
            else:
                fitted[priority_item] = self._truncate(
                    components[priority_item],
                    max_tokens=budget // 2
                )
                budget -= budget // 2

        return fitted
```

### 2.4 Retriever

```python
class AgentRetriever:
    """
    Fetch relevant knowledge, memories, và history.
    Chiến lược: relevance + recency + trust_score.
    """

    async def retrieve_knowledge(
        self,
        intent: Intent,
        context_blocks: dict,
        max_tokens: int = 1000
    ) -> list[KnowledgeChunk]:

        # Determine what knowledge to retrieve
        search_queries = self._intent_to_queries(intent, context_blocks)

        # Current: keyword-based lookup in KB
        # Future: vector similarity search via EmbeddingProvider
        results = []
        for query in search_queries:
            chunks = await knowledge_base.search(
                query=query,
                max_results=3,
                min_trust_score=0.75
            )
            results.extend(chunks)

        # Deduplicate and rank
        ranked = self._rank_and_deduplicate(results)

        # Fit within token budget
        return self._fit_chunks_within_budget(ranked, max_tokens)

    def _intent_to_queries(self, intent: Intent, context: dict) -> list[str]:
        """Map intent to knowledge search queries"""
        queries = []
        if intent.type == "EXPLAIN_LAB":
            for lab in context.get("recent_labs", {}).get("labs", []):
                queries.append(f"lab interpretation {lab['test_name']}")
                queries.append(f"reference range {lab['test_name']}")
        if intent.type == "EXPLAIN_MEDICATION":
            for med in context.get("active_medications", {}).get("medications", []):
                queries.append(f"medication {med['generic_name']} information")
                queries.append(f"drug-lab interaction {med['generic_name']}")
        return queries
```

### 2.5 Knowledge Resolver

```python
class KnowledgeResolver:
    """
    Resolve ambiguous terms, normalize units, lookup references.
    Bridge between user language and KB canonical terms.
    """

    async def resolve(
        self,
        term: str,
        context_type: str = "analyte"
    ) -> ResolutionResult:

        if context_type == "analyte":
            canonical = analyte_resolver.resolve(term)
            if canonical:
                return ResolutionResult(
                    resolved=True,
                    canonical=canonical,
                    alternative_names=LAB_ANALYTE_ALIASES.get(canonical, [])
                )

        if context_type == "condition":
            normalized = medical_term_normalizer.normalize_condition(term)
            return ResolutionResult(
                resolved=normalized.icd10 is not None,
                canonical=normalized.canonical_en,
                icd10=normalized.icd10,
                display_vi=normalized.canonical_vi
            )

        if context_type == "medication":
            drug = await knowledge_base.lookup_drug_by_name(term)
            if drug:
                return ResolutionResult(
                    resolved=True,
                    canonical=drug.generic_name,
                    brand_names=drug.brand_names_vn
                )

        return ResolutionResult(resolved=False, canonical=None)

    async def retrieve_for_intent(
        self,
        intent: Intent,
        max_tokens: int = 1000
    ) -> list[KnowledgeChunk]:
        """High-level: get all knowledge relevant to this intent"""
        queries = self._intent_to_queries(intent)
        chunks = []
        for q in queries:
            result = await knowledge_base.search(q, max_results=2)
            chunks.extend(result)
        return self._deduplicate_and_budget(chunks, max_tokens)
```

### 2.6 Memory Resolver

```python
class MemoryResolver:
    """
    Fetch relevant memories, score, inject into context.
    See 10_MEMORY_ENGINE.md for full memory spec.
    """

    async def resolve_for_request(
        self,
        user_id: str,
        current_query: str,
        context: dict
    ) -> MemoryResolutionResult:

        # Get top-k memories
        memories = await memory_engine.get_top_k_memories(
            user_id=user_id,
            context=context,
            query=current_query,
            k=8
        )

        # Filter by hallucination guard
        safe_memories = [
            m for m in memories
            if hallucination_guard.should_inject(m, context)
        ]

        # Build prompt block
        memory_block = await memory_engine.build_memory_prompt_block(
            user_id=user_id,
            memories=safe_memories
        )

        return MemoryResolutionResult(
            memories=safe_memories,
            prompt_block=memory_block,
            preferred_address=self._extract_preferred_address(safe_memories)
        )
```

### 2.7 Tool Selector

```python
class ToolSelector:
    """
    Chọn tools phù hợp từ registry (12 tools từ 09_TOOLS_AND_ACTIONS.md).
    Kiểm tra permissions trước khi include tool schema trong prompt.
    """

    async def get_available_schemas(
        self,
        screen_id: str,
        user_consent: UserConsent,
        context_blocks_available: list[str]
    ) -> list[dict]:

        available = []
        for tool in tool_registry.get_all():
            # Screen filter
            if tool.available_on_screens and screen_id not in tool.available_on_screens:
                continue

            # Context requirements
            if not all(b in context_blocks_available for b in tool.requires_context_blocks):
                continue

            # Permission check
            if not self._user_has_permissions(tool.permission_scope, user_consent):
                continue

            available.append(tool.to_llm_schema())

        return available

    def _user_has_permissions(
        self,
        required_scope: list[str],
        consent: UserConsent
    ) -> bool:
        SCOPE_CONSENT_MAP = {
            "medications:read": consent.medications_granted,
            "reminders:write": True,           # No special consent for reminders
            "labs:read": consent.lab_results_granted,
            "metrics:write": consent.metrics_granted,
            "care_plan:read": consent.care_plan_granted,
            "care_plan:write": consent.care_plan_granted,
            "appointments:read": True,
        }
        return all(SCOPE_CONSENT_MAP.get(scope, False) for scope in required_scope)
```

### 2.8 Action Validator

```python
class ActionValidator:
    """
    Validate tool inputs trước khi execute.
    Double-check safety và consent at execution time.
    """

    async def validate(
        self,
        tool_call: ToolCall,
        context: AssembledContext,
        user_consent: UserConsent
    ) -> ValidationResult:

        # 1. Schema validation
        schema_valid = tool_registry.validate_args(
            tool_call.name,
            tool_call.arguments
        )
        if not schema_valid:
            return ValidationResult(
                valid=False,
                reason="invalid_schema",
                message="Tool arguments không hợp lệ"
            )

        # 2. Scope guard — check tool is still in scope
        scope_guard = ScopeGuard()
        scope_result = scope_guard.validate_tool_call(tool_call, context)
        if not scope_result.is_valid:
            return ValidationResult(
                valid=False,
                reason="scope_violation",
                message=scope_result.violation_detail
            )

        # 3. Re-check consent at execution time
        if not self._verify_consent_at_execution(tool_call, user_consent):
            return ValidationResult(
                valid=False,
                reason="consent_required",
                message="Cần đồng ý trước khi thực hiện hành động này"
            )

        # 4. Rate limit check
        if await rate_limiter.is_exceeded(tool_call.name, context.user_id):
            return ValidationResult(
                valid=False,
                reason="rate_limited",
                message="Quá nhiều yêu cầu. Vui lòng thử lại sau vài phút."
            )

        return ValidationResult(valid=True)
```

### 2.9 Safety Guard

```python
class SafetyGuard:
    """
    Pre-execution và post-execution safety check.
    Pre: chạy TRƯỚC khi gọi LLM (check input)
    Post: chạy SAU khi có response (check output)
    """

    async def pre_execution_check(
        self,
        user_message: str,
        context: AssembledContext
    ) -> PreCheckResult:

        # 1. Red flag detection (Layer 1 — hardcoded, từ 04_SAFETY_PRIVACY.md)
        has_red_flag, severity, phrase = check_red_flags(user_message)
        if has_red_flag:
            if severity == "emergency":
                return PreCheckResult(
                    action="BYPASS_AI_EMERGENCY",
                    emergency_response=build_escalation_response("emergency", {}, phrase)
                )
            elif severity == "urgent":
                return PreCheckResult(
                    action="PROCEED_WITH_ESCALATION_CONTEXT",
                    escalation_note=f"urgent_symptom:{phrase}"
                )

        # 2. Safety flags from context
        safety_flags = context.blocks.get("safety_flags", {})
        should_escalate, escalation_response = should_override_with_escalation(
            safety_flags, user_message
        )
        if should_escalate:
            return PreCheckResult(
                action="BYPASS_AI_EMERGENCY",
                emergency_response=escalation_response
            )

        # 3. Content moderation (via ModerationProvider)
        moderation_result = await moderation_provider.check(user_message)
        if moderation_result.flagged:
            return PreCheckResult(
                action="BLOCK",
                reason=moderation_result.reason
            )

        return PreCheckResult(action="PROCEED")

    async def post_execution_check(
        self,
        response: str,
        context: AssembledContext
    ) -> PostCheckResult:

        # 1. Grounding validation (from 14_CLINICAL_REASONING.md)
        grounding_result = GroundingEnforcer().validate_response(response, context.to_dict())
        if not grounding_result.is_valid:
            return PostCheckResult(
                action="REVISE",
                issues=grounding_result.issues,
                revision_instruction=self._build_revision_instruction(grounding_result.issues)
            )

        # 2. Scope guard on output
        scope_result = ScopeGuard().validate(response)
        if not scope_result.is_valid:
            return PostCheckResult(
                action="REPLACE",
                replacement=self._build_safe_replacement(response, scope_result.violations)
            )

        # 3. Personal data leak check
        if self._contains_leaked_health_data(response, context):
            return PostCheckResult(
                action="REDACT",
                reason="health_data_leak_detected"
            )

        return PostCheckResult(action="ACCEPT")
```

### 2.10 Response Composer

```python
class ResponseComposer:
    """
    Format response theo personality guide và user preferences.
    Input: raw reasoning/tool results
    Output: formatted, personalized Meto response
    """

    async def compose(
        self,
        raw_content: str | list[str],
        intent: Intent,
        memory_resolution: MemoryResolutionResult,
        context: AssembledContext,
        escalation_level: EscalationLevel | None = None
    ) -> ComposedResponse:

        preferred_address = memory_resolution.preferred_address

        # Apply personality (from 05_PERSONALITY_GUIDE.md)
        formatted = await self.personality_formatter.format(
            content=raw_content,
            preferred_address=preferred_address,
            explanation_style=memory_resolution.get("explanation_style", "simple"),
            tone=self._determine_tone(escalation_level, intent),
        )

        # Add required disclaimers
        if intent.type in CLINICAL_INTENTS:
            formatted += self._clinical_disclaimer(preferred_address)

        # Add "see doctor" section if applicable
        if self._requires_doctor_section(intent, escalation_level):
            formatted += self._doctor_section(
                preferred_address,
                context.blocks.get("today_context", {}).get("upcoming_appointments", [])
            )

        # Add quick action suggestions
        quick_actions = await self._generate_quick_actions(intent, context)

        return ComposedResponse(
            text=formatted,
            quick_actions=quick_actions,
            streaming_supported=True,
            escalation_level=escalation_level
        )
```

### 2.11 Audit Logger

```python
class AgentAuditLogger:
    """
    Log mọi step trong agent execution.
    Không log nội dung sensitive — chỉ metadata.
    """

    async def log_agent_execution(
        self,
        execution_trace: AgentExecutionTrace
    ) -> str:
        """Returns audit_id"""

        entry = AgentAuditEntry(
            session_id=execution_trace.session_id,
            user_id=execution_trace.user_id,
            intent_classified=execution_trace.intent.type,
            plan_steps=len(execution_trace.plan.steps),
            tools_called=[s.tool_name for s in execution_trace.steps if s.tool_name],
            tool_call_count=execution_trace.tool_call_count,
            reasoning_called=execution_trace.reasoning_called,
            crl_called=execution_trace.crl_called,
            re_called=execution_trace.re_called,
            dhe_called=execution_trace.dhe_called,
            escalation_level=execution_trace.escalation_level,
            provider_used=execution_trace.provider_used,
            total_execution_ms=execution_trace.total_ms,
            token_count_input=execution_trace.tokens_in,
            token_count_output=execution_trace.tokens_out,
            fallback_used=execution_trace.fallback_used,
            error_occurred=execution_trace.error is not None,
            safety_check_pre=execution_trace.pre_check_result,
            safety_check_post=execution_trace.post_check_result,
            created_at=utcnow()
        )

        await db.insert("agent_audit_logs", entry)
        return entry.id
```

### 2.12 Analytics Collector

```python
class AgentAnalyticsCollector:
    """
    Emit analytics events per step.
    Non-blocking, best-effort (không block response nếu analytics fail).
    """

    async def emit(self, event_name: str, properties: dict, user_id: str):
        """Fire-and-forget analytics event"""
        asyncio.create_task(
            self._emit_internal(event_name, properties, user_id)
        )

    async def _emit_internal(self, event_name: str, properties: dict, user_id: str):
        try:
            # Anonymize user_id for analytics
            anon_id = hashlib.sha256(user_id.encode()).hexdigest()[:16]
            await analytics_backend.track(
                event=event_name,
                properties={**properties, "user_anon_id": anon_id},
                timestamp=utcnow()
            )
        except Exception as e:
            logger.warning(f"Analytics emit failed: {e}")  # Never raise

ANALYTICS_EVENTS = [
    "agent.intent_classified",
    "agent.plan_created",
    "agent.tool_selected",
    "agent.tool_executed",
    "agent.tool_confirmed",
    "agent.tool_cancelled",
    "agent.crl_executed",
    "agent.recommendation_generated",
    "agent.escalation_triggered",
    "agent.response_delivered",
    "agent.fallback_used",
    "agent.error_occurred",
    "agent.user_feedback_received",
]
```

### 2.13 State Manager

```python
class AgentStateManager:
    """
    Quản lý conversation state, agent state, và recovery state.
    """

    class AgentState(str, Enum):
        IDLE = "idle"
        PLANNING = "planning"
        RETRIEVING = "retrieving"
        REASONING = "reasoning"
        TOOL_PENDING_CONFIRMATION = "tool_pending_confirmation"
        TOOL_EXECUTING = "tool_executing"
        COMPOSING = "composing"
        STREAMING = "streaming"
        ERROR = "error"
        ESCALATING = "escalating"

    async def get_state(self, session_id: str) -> AgentState:
        raw = await redis.get(f"agent:state:{session_id}")
        return AgentState(raw) if raw else AgentState.IDLE

    async def set_state(self, session_id: str, state: AgentState):
        await redis.setex(f"agent:state:{session_id}", 3600, state.value)

    async def save_recovery_checkpoint(
        self,
        session_id: str,
        checkpoint: RecoveryCheckpoint
    ):
        """Save mid-execution state for recovery"""
        await redis.setex(
            f"agent:checkpoint:{session_id}",
            1800,  # 30 minutes TTL
            checkpoint.json()
        )

    async def get_recovery_checkpoint(
        self,
        session_id: str
    ) -> RecoveryCheckpoint | None:
        raw = await redis.get(f"agent:checkpoint:{session_id}")
        return RecoveryCheckpoint.parse_raw(raw) if raw else None
```

### 2.14 Fallback Manager

```python
class FallbackManager:
    """
    Provider fallback, tool fallback, graceful degradation.
    """

    async def handle_provider_failure(
        self,
        error: ProviderError,
        original_request: LLMRequest,
        fallback_chain: list[str]  # ["claude", "openai", "local"]
    ) -> LLMResponse | None:

        for provider_name in fallback_chain[1:]:  # Skip failed primary
            try:
                provider = provider_registry.get(provider_name)
                response = await provider.complete(original_request)
                await analytics.emit("agent.fallback_used", {
                    "failed_provider": fallback_chain[0],
                    "fallback_provider": provider_name,
                    "reason": str(error)
                })
                return response
            except ProviderError:
                continue

        # All providers failed — graceful degradation
        return self._build_degraded_response(original_request)

    def _build_degraded_response(self, request: LLMRequest) -> LLMResponse:
        """Response when all providers fail"""
        return LLMResponse(
            content=(
                "Meto đang gặp sự cố kỹ thuật tạm thời. "
                "Vui lòng thử lại sau ít phút. "
                "Nếu cần hỗ trợ khẩn, hãy liên hệ trực tiếp với bác sĩ."
            ),
            is_degraded=True
        )

    async def handle_tool_failure(
        self,
        tool_call: ToolCall,
        error: ToolError
    ) -> ToolFallbackResult:

        # Retry once if transient error
        if error.is_transient and error.retry_count < 1:
            return ToolFallbackResult(action="RETRY")

        # Skip optional tool, continue without it
        if tool_registry.get(tool_call.name).is_optional:
            return ToolFallbackResult(action="SKIP")

        # Required tool failed → inform user gracefully
        return ToolFallbackResult(
            action="INFORM",
            user_message=(
                f"Meto không thể thực hiện '{tool_registry.get(tool_call.name).display_name}' "
                f"lúc này. Vui lòng thử lại sau."
            )
        )
```

### 2.15 Error Recovery

```python
class ErrorRecovery:
    """
    Retry logic và partial failure handling.
    """

    RETRY_CONFIG = {
        "provider_timeout": {"max_retries": 2, "delay_ms": 1000},
        "provider_rate_limit": {"max_retries": 3, "delay_ms": 5000},
        "tool_timeout": {"max_retries": 1, "delay_ms": 500},
        "tool_validation_error": {"max_retries": 0, "delay_ms": 0},
    }

    async def recover(
        self,
        error: AgentError,
        checkpoint: RecoveryCheckpoint | None
    ) -> RecoveryResult:

        retry_config = self.RETRY_CONFIG.get(error.error_type, {"max_retries": 0})

        if error.retry_count < retry_config["max_retries"]:
            await asyncio.sleep(retry_config["delay_ms"] / 1000)
            return RecoveryResult(action="RETRY", from_checkpoint=checkpoint)

        # Partial failure: if some steps completed, use partial results
        if checkpoint and checkpoint.completed_steps:
            return RecoveryResult(
                action="PARTIAL_RESPONSE",
                use_partial_results=True,
                checkpoint=checkpoint
            )

        # Complete failure
        return RecoveryResult(
            action="GRACEFUL_DEGRADATION",
            degraded_response=fallback_manager._build_degraded_response(error.request)
        )
```

---

## 3. Sequence Diagrams

### 3.1 Happy Path: User Message → Full Agent Loop → Response

```
User        Frontend    API     SafetyGuard  ContextBuilder  AgentPlanner  Reasoner  ResponseComposer  StreamingResponse
 │              │        │           │              │               │           │             │                │
 │ [send msg]   │        │           │              │               │           │             │                │
 ├─────────────▶│        │           │              │               │           │             │                │
 │              │ POST   │           │              │               │           │             │                │
 │              ├───────▶│           │              │               │           │             │                │
 │              │        │ pre_check │              │               │           │             │                │
 │              │        ├──────────▶│              │               │           │             │                │
 │              │        │ OK        │              │               │           │             │                │
 │              │        │◀──────────│              │               │           │             │                │
 │              │        │           │ build()      │               │           │             │                │
 │              │        ├────────────────────────▶│               │           │             │                │
 │              │        │           │ context      │               │           │             │                │
 │              │        │◀────────────────────────│               │           │             │                │
 │              │        │           │              │  plan()       │           │             │                │
 │              │        ├──────────────────────────────────────▶│           │             │                │
 │              │        │           │              │  ExecutionPlan│           │             │                │
 │              │        │◀──────────────────────────────────────│           │             │                │
 │              │        │           │              │               │ reason()  │             │                │
 │              │        ├──────────────────────────────────────────────────▶│             │                │
 │              │        │           │              │               │ result    │             │                │
 │              │        │◀──────────────────────────────────────────────────│             │                │
 │              │        │           │ post_check   │               │           │             │                │
 │              │        ├──────────▶│              │               │           │             │                │
 │              │        │ OK        │              │               │           │             │                │
 │              │        │◀──────────│              │               │           │             │                │
 │              │        │           │              │               │           │  compose()  │                │
 │              │        ├──────────────────────────────────────────────────────────────▶│                │
 │              │        │           │              │               │           │  response   │                │
 │              │        │◀──────────────────────────────────────────────────────────────│                │
 │              │        │           │              │               │           │             │ stream_start   │
 │              │        ├───────────────────────────────────────────────────────────────────────────────▶│
 │  [streaming] │        │           │              │               │           │             │                │
 │◀─────────────│◀───────────────────────────────────────────────────────────────────────────────────────│
 │  [complete]  │        │           │              │               │           │             │                │
```

### 3.2 Tool Use Path

```
User    AgentPlanner  ToolSelector  ActionValidator  ToolEngine  SafetyGuard  ResponseComposer
 │           │              │               │              │            │               │
 │ [create   │              │               │              │            │               │
 │  reminder]│              │               │              │            │               │
 ├──────────▶│              │               │              │            │               │
 │           │ get_schemas()│               │              │            │               │
 │           ├─────────────▶│              │              │            │               │
 │           │ [tool schemas]│              │              │            │               │
 │           │◀─────────────│              │              │            │               │
 │           │ [AI selects tool: create_reminder]         │            │               │
 │           │              │ validate()   │              │            │               │
 │           ├──────────────────────────▶│              │            │               │
 │           │              │ VALID        │              │            │               │
 │           │              │◀──────────────             │            │               │
 │           │ [user confirmation needed]                │            │               │
 │◀──────────│ "Meto sẽ tạo nhắc nhở... Đồng ý?"       │            │               │
 │           │              │               │              │            │               │
 │ [confirm] │              │               │              │            │               │
 ├──────────▶│              │               │              │            │               │
 │           │              │               │ execute()    │            │               │
 │           ├──────────────────────────────────────────▶│            │               │
 │           │              │               │ ToolResult   │            │               │
 │           │◀──────────────────────────────────────────│            │               │
 │           │ inject tool result into conversation       │            │               │
 │           │              │               │              │  post_check│               │
 │           ├──────────────────────────────────────────────────────▶│               │
 │           │              │               │              │  OK        │               │
 │           │◀──────────────────────────────────────────────────────│               │
 │           │              │               │              │            │  compose()    │
 │           ├──────────────────────────────────────────────────────────────────────▶│
 │           │              │               │              │            │  response     │
 │           │◀──────────────────────────────────────────────────────────────────────│
 │ [response]│              │               │              │            │               │
 │◀──────────│              │               │              │            │               │
```

### 3.3 Error + Fallback Path

```
User    AgentPlanner  ProviderAbstraction  FallbackManager  ErrorRecovery  ResponseComposer
 │           │                │                   │               │               │
 │ [message] │                │                   │               │               │
 ├──────────▶│                │                   │               │               │
 │           │ llm_call()     │                   │               │               │
 │           ├───────────────▶│                   │               │               │
 │           │                │ [Provider A Timeout]              │               │
 │           │                │◀ ProviderError    │               │               │
 │           │ handle_failure()                   │               │               │
 │           ├───────────────────────────────────▶│               │               │
 │           │                │ try_fallback(B)    │               │               │
 │           │                │◀───────────────────│               │               │
 │           │                │ [Provider B: 429 Rate Limited]     │               │
 │           │                │◀─ ProviderError   │               │               │
 │           │                │ try_fallback(C)    │               │               │
 │           │                │◀───────────────────│               │               │
 │           │                │ [Provider C: OK]   │               │               │
 │           │ response       │                   │               │               │
 │           │◀───────────────│                   │               │               │
 │           │                │                   │ recover()     │               │
 │           ├──────────────────────────────────────────────────▶│               │
 │           │                │                   │ RecoveryResult│               │
 │           │◀──────────────────────────────────────────────────│               │
 │           │                │                   │               │  compose()    │
 │           ├──────────────────────────────────────────────────────────────────▶│
 │ [response + "đã dùng kết nối dự phòng" note]  │               │               │
 │◀──────────│                │                   │               │               │
```

### 3.4 Agent State Diagram

```
                ┌─────────────────────────────────────────────────────────────┐
                │                    AGENT STATE MACHINE                       │
                │                                                              │
                │           user_message                                       │
                │  ┌──────────────────────────────────────────┐               │
                │  │            ┌─────────────────┐           │               │
                │  │            │      IDLE        │           │               │
                │  │            └────────┬─────────┘           │               │
                │  │                     │ user_message         │               │
                │  │                     ▼                      │               │
                │  │           ┌──────────────────┐            │               │
                │  │           │    PLANNING      │            │               │
                │  │           └────────┬─────────┘            │               │
                │  │                     │ plan_ready           │               │
                │  │                     ▼                      │               │
                │  │           ┌──────────────────┐            │               │
                │  │           │   RETRIEVING     │            │               │
                │  │           └────────┬─────────┘            │               │
                │  │                     │ retrieval_done       │               │
                │  │          ┌──────────┴────────────┐        │               │
                │  │          │         │             │        │               │
                │  │          ▼         ▼             ▼        │               │
                │  │  ┌──────────┐ ┌─────────┐ ┌─────────┐   │               │
                │  │  │REASONING │ │  TOOL   │ │COMPOSING│   │               │
                │  │  │          │ │PENDING_ │ └────┬────┘   │               │
                │  │  └────┬─────┘ │CONFIRM │       │        │               │
                │  │       │       └────┬────┘       │        │               │
                │  │       │  user_     │confirm     │        │               │
                │  │       │  confirms  │            ▼        │               │
                │  │       │       ┌────▼────┐  ┌──────────┐ │               │
                │  │       └──────▶│  TOOL   │  │STREAMING │ │               │
                │  │               │EXECUTING│  │          │ │               │
                │  │               └────┬────┘  └────┬─────┘ │               │
                │  │                    │complete    │done    │               │
                │  │                    └─────┬──────┘        │               │
                │  │                          │               │               │
                │  │                    ┌─────▼─────┐        │               │
                │  │                    │    IDLE    │        │               │
                │  │                    └────────────┘        │               │
                │  │                                          │               │
                │  │  ERROR path:                             │               │
                │  │  Any state → ERROR → ErrorRecovery → IDLE or DEGRADED   │
                │  └──────────────────────────────────────────┘               │
                └─────────────────────────────────────────────────────────────┘
```

---

## 4. Full Agent Loop — Code Flow

```python
class MetoAgent:
    """
    Orchestrates all agent components for a single request.
    """

    async def process(
        self,
        user_message: str,
        session: ConversationSession,
        user_id: str
    ) -> AsyncGenerator[str, None]:

        # Initialize execution trace
        trace = AgentExecutionTrace(
            session_id=session.session_id,
            user_id=user_id,
        )

        try:
            # Step 1: Safety pre-check (Layer 1 — hardcoded)
            await state_manager.set_state(session.session_id, AgentState.PLANNING)
            pre_check = await safety_guard.pre_execution_check(user_message, context=None)

            if pre_check.action == "BYPASS_AI_EMERGENCY":
                yield pre_check.emergency_response
                await audit_logger.log_agent_execution(trace)
                return

            # Step 2: Build context
            await state_manager.set_state(session.session_id, AgentState.RETRIEVING)
            context = await context_builder.build(
                user_id=user_id,
                screen_id=session.screen_id,
                user_message=user_message,
                session=session,
                intent=Intent()  # Pre-intent for context build
            )
            trace.context_blocks_used = list(context.blocks.keys())

            # Step 3: Safety pre-check with full context (Layer 1 + Layer 2)
            pre_check_full = await safety_guard.pre_execution_check(user_message, context)
            if pre_check_full.action in ("BYPASS_AI_EMERGENCY", "BLOCK"):
                yield pre_check_full.emergency_response or pre_check_full.block_message
                return

            # Step 4: Plan
            intent = await planner.classify_intent(user_message, context)
            plan = await planner.plan(user_message, context, memory_resolution.memories, session)
            trace.intent = intent
            trace.plan = plan

            # Step 5: Execute plan steps
            step_results = []
            for step in plan.steps:

                if step.action == "retrieve":
                    result = await retriever.retrieve_knowledge(intent, context)
                    step_results.append(StepResult(step=step, result=result))

                elif step.action == "reason":
                    await state_manager.set_state(session.session_id, AgentState.REASONING)
                    result = await reasoner.reason(
                        query=user_message,
                        context=context,
                        knowledge_chunks=self._get_knowledge(step_results),
                        memory=memory_resolution.memories,
                        previous_steps=step_results
                    )
                    step_results.append(StepResult(step=step, result=result))
                    trace.reasoning_called = True

                elif step.action == "clinical_reasoning":
                    crl_output = await clinical_reasoning_layer.reason(context)
                    step_results.append(StepResult(step=step, result=crl_output))
                    trace.crl_called = True

                elif step.action == "recommendation":
                    rec_output = await recommendation_engine.generate(context, crl_output)
                    step_results.append(StepResult(step=step, result=rec_output))
                    trace.re_called = True

                elif step.action == "call_tool":
                    # Need user confirmation if required
                    tool_def = tool_registry.get(step.tool_name)
                    if tool_def.requires_consent:
                        await state_manager.set_state(
                            session.session_id,
                            AgentState.TOOL_PENDING_CONFIRMATION
                        )
                        # Stream confirmation request
                        yield self._build_confirmation_request(tool_def, step.tool_args)
                        # Wait for user confirmation (handled by next request)
                        return  # Will be resumed in next request cycle

                    await state_manager.set_state(session.session_id, AgentState.TOOL_EXECUTING)
                    validation = await action_validator.validate(
                        ToolCall(name=step.tool_name, arguments=step.tool_args),
                        context,
                        session.user_consent
                    )
                    if not validation.valid:
                        step_results.append(StepResult(step=step, result=ToolError(validation.reason)))
                        continue

                    tool_result = await tool_engine.execute(step.tool_name, step.tool_args)
                    step_results.append(StepResult(step=step, result=tool_result))
                    trace.tool_call_count += 1

            # Step 6: Doctor handoff check
            escalation_result = await doctor_handoff_engine.assess(
                step_results=step_results,
                symptoms_in_message=extract_symptoms(user_message)
            )
            trace.escalation_level = escalation_result.level
            trace.dhe_called = True

            # Step 7: Compose response
            await state_manager.set_state(session.session_id, AgentState.COMPOSING)
            response = await response_composer.compose(
                raw_content=self._synthesize_results(step_results),
                intent=intent,
                memory_resolution=memory_resolution,
                context=context,
                escalation_level=escalation_result.level
            )

            # Step 8: Post-execution safety check
            post_check = await safety_guard.post_execution_check(response.text, context)
            if post_check.action == "REVISE":
                response = await self._revise_response(response, post_check.revision_instruction)
            elif post_check.action == "REPLACE":
                response.text = post_check.replacement

            # Step 9: Stream response
            await state_manager.set_state(session.session_id, AgentState.STREAMING)
            async for chunk in self._stream_response(response.text):
                yield chunk

            # Step 10: Post-execution tasks (non-blocking)
            asyncio.create_task(self._post_execution_tasks(
                session=session,
                response=response,
                step_results=step_results,
                trace=trace,
                escalation_result=escalation_result
            ))

        except Exception as e:
            # Error recovery
            recovery = await error_recovery.recover(
                AgentError(error=e, request_id=session.session_id),
                await state_manager.get_recovery_checkpoint(session.session_id)
            )
            if recovery.action == "RETRY":
                yield await self._retry_with_checkpoint(recovery.checkpoint)
            else:
                yield fallback_manager._build_degraded_response(None).content

        finally:
            await state_manager.set_state(session.session_id, AgentState.IDLE)
            await audit_logger.log_agent_execution(trace)

    async def _post_execution_tasks(self, **kwargs):
        """Non-blocking post-execution tasks"""
        await asyncio.gather(
            memory_collector.extract_and_store(kwargs["session"], kwargs["step_results"]),
            analytics_collector.emit("agent.response_delivered", {
                "intent": kwargs["trace"].intent.type,
                "escalation": kwargs["escalation_result"].level,
            }, kwargs["session"].user_id),
            doctor_handoff_engine.schedule_followup_if_needed(kwargs["escalation_result"]),
        )
```

---

## 5. Future Compatibility

### 5.1 MCP (Model Context Protocol) Compatibility

```python
class MCPCompatibilityLayer:
    """
    Thiết kế để tương thích với MCP cho future multi-agent communication.
    """

    MCP_VERSION = "1.0"

    def export_tool_as_mcp(self, tool: ToolDefinition) -> MCPTool:
        return MCPTool(
            name=f"meto.{tool.mcp_namespace}.{tool.name}",
            description=tool.description,
            inputSchema=tool.parameters_schema,
            annotations={
                "meto_version": "1.0",
                "safety_level": "medical_assistant",
                "requires_consent": tool.requires_consent,
            }
        )

    def export_agent_as_mcp_server(self) -> MCPServer:
        """Expose Meto as an MCP server for future multi-agent integration"""
        return MCPServer(
            name="meto-health-companion",
            version="1.0",
            tools=[self.export_tool_as_mcp(t) for t in tool_registry.get_all()],
            capabilities=["health_context", "clinical_reasoning", "recommendations"],
        )
```

### 5.2 Multi-Agent Architecture — Future

```
FUTURE ARCHITECTURE (Phase 5+):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Orchestrator Agent (Meto Core)
    │
    ├── Patient Agent (current Meto)
    │   └── Handles patient-facing conversations
    │
    ├── Doctor Agent (future)
    │   └── Doctor-facing dashboard, clinical summary generation
    │   └── Requires doctor authentication
    │   └── Access to aggregated patient summaries (anonymized cohort)
    │
    ├── Caregiver Agent (future)
    │   └── Family member with patient consent
    │   └── Limited view (summary only, no raw data without consent)
    │   └── Care coordination features
    │
    └── Research Agent (future)
        └── Anonymized cohort analysis
        └── Population health trends
        └── Privacy: no individual patient data, only aggregates
```

### 5.3 Future Agent Registry

```python
AGENT_REGISTRY = {
    "patient_agent": {
        "status": "active",
        "description": "Current Meto — patient-facing health companion",
        "permissions": "patient_own_data_only",
        "mcp_compatible": True,
    },
    "doctor_agent": {
        "status": "planned_q4_2026",
        "description": "Doctor-facing clinical intelligence agent",
        "permissions": "doctor_dashboard_only",
        "requires": "medical_professional_verification",
        "mcp_compatible": True,
    },
    "caregiver_agent": {
        "status": "planned_2027",
        "description": "Family caregiver with patient consent",
        "permissions": "patient_consent_gated",
        "mcp_compatible": True,
    },
    "research_agent": {
        "status": "future",
        "description": "Anonymized research and analytics",
        "permissions": "anonymized_aggregated_only",
        "requires": "IRB_approval",
    }
}
```

---

## 6. Acceptance Criteria

### AC-AOL-001: Core Loop
- [ ] Full agent loop completes in < 5 seconds P95 for simple queries
- [ ] Tool execution with confirmation completes within same session turn
- [ ] State machine transitions are atomic (no inconsistent states)
- [ ] Emergency bypass: latency < 200ms (no LLM call, hardcoded response)

### AC-AOL-002: Safety
- [ ] Pre-execution safety check runs before every LLM call
- [ ] Post-execution safety check runs before every response delivery
- [ ] Self-critique detects diagnosis statements in >95% of test cases
- [ ] Scope violations never reach user in production (post-check blocks)

### AC-AOL-003: Fallback
- [ ] Provider fallback: max 2 fallback attempts before degraded response
- [ ] Degraded response always includes emergency contact guidance
- [ ] Tool failure (non-critical) → graceful skip, user informed

### AC-AOL-004: Audit
- [ ] Every request creates audit entry with execution trace
- [ ] Tool calls: every call logged with tool_name + result
- [ ] Escalation events: logged with urgency score and triggers

### AC-AOL-005: Performance
- [ ] Analytics events emitted non-blocking (agent not slowed)
- [ ] Memory post-collection runs async, not blocking response
- [ ] Context assembly parallelized (asyncio.gather for all blocks)

### AC-AOL-006: Future Compatibility
- [ ] All 12 tools export valid MCP tool schemas
- [ ] Agent state machine documented and testable
- [ ] Recovery checkpoint schema versioned and forward-compatible

---

*Xem thêm: 14_CLINICAL_REASONING.md, 15_RECOMMENDATION_ENGINE.md, 17_DOCTOR_HANDOFF.md, 18_MULTIMODAL.md (tất cả được orchestrate bởi AOL), 20_PROVIDER_ABSTRACTION.md (LLM calls trong AOL dùng Provider Abstraction)*
