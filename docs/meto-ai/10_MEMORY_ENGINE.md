# Meto AI — Memory Engine Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Memory Engine cho phép Meto **nhớ người dùng qua các session** — phong cách giao tiếp ưa thích, mục tiêu sức khỏe, chủ đề hay quan tâm, và thông tin tiết lộ trong chat. Khác với Context Engine (load data từ DB sức khỏe), Memory Engine học từ chính quá trình tương tác với Meto.

**Mục tiêu:** Mỗi lần user mở chat mới, Meto không cần "làm quen lại từ đầu" — nhớ user ưa được gọi là gì, ưa giải thích đơn giản hay chi tiết, đang lo lắng về điều gì.

**File backend:**
- `app/ai/memory_engine.py` — Core retrieval + ranking
- `app/ai/memory_collector.py` — Extract & store memories từ conversations
- `app/models/memory.py` — DB models
- `app/api/memory.py` — User-facing API (xem, sửa, xóa)

---

## 1. Memory Tiers

### 1.1 Tier 1 — Short-term (In-session)

```python
@dataclass
class ShortTermMemory:
    """
    Sống trong session hiện tại.
    Lưu trong Redis, TTL = session lifetime.
    Không persist sang session tiếp theo tự động —
    Memory Collector quyết định có nâng lên Medium-term không.
    """
    session_id: str
    user_id: str
    
    # Key-value facts đã được detect trong session này
    facts: dict[str, Any]
    # VD: {
    #   "currently_discussing": "HbA1c_interpretation",
    #   "user_emotional_state": "concerned",
    #   "preferred_detail_level_today": "detailed",
    #   "entities_mentioned": ["Metformin", "HbA1c", "BS. Trần Minh Khoa"]
    # }
    
    created_at: datetime
    ttl_seconds: int = 3600  # 1 giờ hoặc bằng session TTL
    
    # Storage: Redis key = f"memory:short:{session_id}"
```

### 1.2 Tier 2 — Medium-term (Cross-session, 30 ngày)

```python
@dataclass  
class MediumTermMemory:
    """
    Cross-session, tồn tại trong 30 ngày.
    Lưu trong PostgreSQL, compressed.
    Được refresh nếu accessed (last_accessed_at refreshes TTL).
    """
    id: str
    user_id: str
    category: MemoryCategory
    key: str                    # Unique per user per category
    value: str                  # Stored as text (serialized JSON nếu complex)
    
    # Scoring
    relevance_score: float      # 0.0 – 1.0
    recency_score: float        # 0.0 – 1.0 (decay over time)
    importance_score: float     # 0.0 – 1.0 (manually set or inferred)
    composite_score: float      # Computed: see scoring formula
    
    # Lifecycle
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    expires_at: datetime        # = created_at + 30 days (refreshed on access)
    
    # Metadata
    source_session_id: str      # Session này was extracted from
    confidence: float           # Confidence score của extraction (0.0-1.0)
    times_confirmed: int = 0    # Bao nhiêu lần user xác nhận / tool verified
    
    # Storage: PostgreSQL table `memory_items`, tier = 'medium'
```

### 1.3 Tier 3 — Long-term (Permanent, user preferences)

```python
@dataclass
class LongTermMemory:
    """
    Permanent user preferences.
    Không tự expire — chỉ xóa khi user chủ động xóa.
    Thường là thông tin user tự cài (preferred_address) hoặc confirmed nhiều lần.
    """
    id: str
    user_id: str
    category: MemoryCategory    # Chủ yếu: PREFERENCE, HEALTH_GOAL
    key: str
    value: str
    
    # Scoring (vẫn có nhưng expires_at = NULL)
    importance_score: float
    composite_score: float
    
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    expires_at: None = None     # NEVER expires
    
    # User editable
    is_user_confirmed: bool = False   # User đã review và xác nhận
    is_user_set: bool = False         # User tự đặt (không phải AI infer)
    
    # Storage: PostgreSQL table `memory_items`, tier = 'long'
```

---

## 2. Memory Categories

```python
class MemoryCategory(str, Enum):
    
    PREFERENCE = "preference"
    """
    Cách xưng hô ưa thích, phong cách giải thích,
    ngôn ngữ sử dụng, tone ưa thích.
    
    VD:
    - preferred_address: "anh" / "chị" / "bác"
    - explanation_style: "simple" / "detailed" / "analogies"  
    - response_length: "concise" / "comprehensive"
    - language_preference: "vi" / "en"
    - tone_preference: "warm" / "professional" / "friendly"
    """
    
    HEALTH_GOAL = "health_goal"
    """
    Mục tiêu sức khỏe, điều lo lắng, thói quen muốn cải thiện.
    
    VD:
    - primary_goal: "Kiểm soát đường huyết dưới 130"
    - main_concern: "Lo biến chứng thận"
    - lifestyle_goal: "Giảm 5kg trong 3 tháng"
    - medication_concern: "Hay quên uống thuốc buổi trưa"
    """
    
    INTERACTION = "interaction"
    """
    Chủ đề hay hỏi, cách giải thích nào hiệu quả với user này,
    pattern tương tác.
    
    VD:
    - frequent_topic: "lab_interpretation"
    - effective_explanation_type: "comparison_based"
    - question_pattern: "often_asks_about_side_effects"
    - session_timing: "usually_mornings"
    """
    
    CONTEXTUAL = "contextual"
    """
    Thông tin tình huống tiết lộ trong chat, không nhất thiết là preference.
    TTL ngắn hơn (7 ngày), không lưu nếu không cần.
    
    VD:
    - recent_concern: "Đang lo về kết quả HbA1c tháng này"
    - upcoming_event: "Có lịch khám 5/7/2026"
    - recent_activity: "Vừa bắt đầu đi bộ buổi sáng"
    """
    
    MEDICAL_PREFERENCE = "medical_preference"
    """
    Cách user muốn nhận thông tin y tế cụ thể.
    
    VD:
    - prefer_analogies_for: ["blood_pressure", "HbA1c"]
    - comfortable_with_medical_terms: false
    - prefers_visual_descriptions: true
    """
```

---

## 3. Memory Scoring

### 3.1 Score Components

```python
class MemoryScorer:
    
    # Weights
    W_RELEVANCE = 0.40
    W_RECENCY = 0.35
    W_IMPORTANCE = 0.25
    
    def compute_relevance_score(
        self,
        memory_key: str,
        memory_value: str,
        current_context: dict,
        current_query: str
    ) -> float:
        """
        Relevance = cosine similarity between memory content và current context/query.
        Dùng lightweight embedding (không phải full LLM call).
        
        Shortcuts:
        - PREFERENCE memories → luôn relevant (base = 0.8)
        - CONTEXTUAL memories → relevant chỉ nếu topic match
        - HEALTH_GOAL memories → relevant nếu current query liên quan đến health goals
        """
        category = self.get_category_from_key(memory_key)
        
        if category == MemoryCategory.PREFERENCE:
            return 0.8  # Always somewhat relevant
        
        if category == MemoryCategory.HEALTH_GOAL:
            # Check if current topic relates to health goals
            if self.topic_overlaps_goal(current_query, memory_value):
                return 0.9
            return 0.3
        
        # Contextual / Interaction: use text similarity
        return self.compute_text_similarity(
            f"{memory_key}: {memory_value}",
            f"{current_query} {json.dumps(current_context)[:500]}"
        )
    
    def compute_recency_score(self, last_accessed_at: datetime) -> float:
        """
        Exponential decay:
        - Today: 1.0
        - 1 week: 0.7
        - 2 weeks: 0.5
        - 30 days: 0.1
        """
        days_ago = (utcnow() - last_accessed_at).days
        return max(0.0, math.exp(-0.05 * days_ago))
    
    def compute_importance_score(
        self,
        memory: MemoryItem,
        source_session: ConversationSession | None = None
    ) -> float:
        """
        Base importance từ category + boosters:
        """
        base_scores = {
            MemoryCategory.PREFERENCE: 0.8,
            MemoryCategory.HEALTH_GOAL: 0.9,
            MemoryCategory.MEDICAL_PREFERENCE: 0.85,
            MemoryCategory.INTERACTION: 0.5,
            MemoryCategory.CONTEXTUAL: 0.3,
        }
        
        score = base_scores.get(memory.category, 0.5)
        
        # Boosters
        if memory.is_user_confirmed:
            score = min(1.0, score + 0.2)
        if memory.is_user_set:
            score = min(1.0, score + 0.3)
        if memory.times_confirmed >= 3:
            score = min(1.0, score + 0.1)
        
        return score
    
    def compute_composite_score(self, memory: MemoryItem, context: dict, query: str) -> float:
        """
        composite = W_R * relevance + W_Rec * recency + W_I * importance
        """
        relevance = self.compute_relevance_score(memory.key, memory.value, context, query)
        recency = self.compute_recency_score(memory.last_accessed_at)
        importance = memory.importance_score
        
        return (
            self.W_RELEVANCE * relevance +
            self.W_RECENCY * recency +
            self.W_IMPORTANCE * importance
        )
```

### 3.2 Memory Ranking

```python
async def get_top_k_memories(
    user_id: str,
    context: dict,
    query: str,
    k: int = 8,
    categories: list[MemoryCategory] | None = None,
    min_composite_score: float = 0.4
) -> list[MemoryItem]:
    
    # Load từ DB (filter expired, filter category)
    candidates = await db.fetch("""
        SELECT * FROM memory_items
        WHERE user_id = :user_id
          AND (expires_at IS NULL OR expires_at > NOW())
          AND (:categories IS NULL OR category = ANY(:categories))
        ORDER BY last_accessed_at DESC
        LIMIT 50  -- Pre-filter top 50 candidates
    """, {"user_id": user_id, "categories": categories})
    
    # Score each
    scorer = MemoryScorer()
    scored = []
    for mem in candidates:
        composite = scorer.compute_composite_score(mem, context, query)
        if composite >= min_composite_score:
            mem.composite_score = composite
            scored.append(mem)
    
    # Sort by composite score
    scored.sort(key=lambda m: m.composite_score, reverse=True)
    
    # Diversity: không lấy quá 3 memories từ cùng category
    result = []
    category_counts: dict[str, int] = {}
    for mem in scored:
        cat_count = category_counts.get(mem.category, 0)
        if cat_count < 3:
            result.append(mem)
            category_counts[mem.category] = cat_count + 1
        if len(result) >= k:
            break
    
    # Update last_accessed_at
    if result:
        ids = [m.id for m in result]
        await db.execute(
            "UPDATE memory_items SET last_accessed_at = NOW() WHERE id = ANY(:ids)",
            {"ids": ids}
        )
    
    return result
```

---

## 4. Memory Extraction — Collector

```python
class MemoryCollector:
    """
    Chạy sau mỗi session kết thúc (SOFT_CLOSED).
    Phân tích conversation history → extract memories → save.
    """
    
    EXTRACTION_PROMPT = """
    Phân tích cuộc trò chuyện sau và extract thông tin cần nhớ về người dùng.
    
    Chỉ extract khi thông tin RÕ RÀNG và ĐÁNG TIN CẬY.
    Không suy luận, không đoán mò.
    
    Format output (JSON):
    {
        "memories": [
            {
                "category": "preference|health_goal|interaction|contextual|medical_preference",
                "key": "snake_case_key",
                "value": "string value",
                "confidence": 0.0-1.0,
                "reasoning": "why this is worth remembering"
            }
        ]
    }
    
    KHÔNG extract:
    - Thông tin đã có trong hồ sơ sức khỏe (chẩn đoán, thuốc, lab)
    - Thông tin nhạy cảm không cần thiết (địa chỉ cụ thể, tên người thân)
    - Triệu chứng cụ thể (chúng được lưu trong symptom_intake)
    - Raw health values (chúng được lưu trong record_metric)
    
    Conversation:
    {conversation_text}
    """
    
    async def extract_and_store(
        self,
        session: ConversationSession,
        messages: list[Message]
    ) -> list[MemoryItem]:
        
        # Only process sessions with enough content
        if len(messages) < 3:
            return []
        
        # Build conversation text for extraction
        conv_text = "\n".join([
            f"[{m.role.upper()}]: {m.content[:500]}"  # Truncate each message
            for m in messages
            if not m.is_summary and m.role in ("user", "assistant")
        ])
        
        # Call AI for extraction (mini call, no tools)
        extracted = await ai_mini_call(
            system=self.EXTRACTION_PROMPT.format(conversation_text=conv_text),
            response_format="json"
        )
        
        saved = []
        for item in extracted.get("memories", []):
            if item["confidence"] < 0.7:
                continue  # Skip low-confidence extractions
            
            # Sanitize before storage
            safe_value = self.sanitize_memory_value(item["value"])
            
            memory = await self.upsert_memory(
                user_id=session.user_id,
                category=item["category"],
                key=item["key"],
                value=safe_value,
                confidence=item["confidence"],
                source_session_id=session.session_id
            )
            saved.append(memory)
        
        return saved
    
    async def upsert_memory(
        self,
        user_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float,
        source_session_id: str
    ) -> MemoryItem:
        """Upsert: nếu đã có memory cùng key → apply update policy"""
        
        existing = await db.fetch_one(
            "SELECT * FROM memory_items WHERE user_id = :uid AND category = :cat AND key = :key",
            {"uid": user_id, "cat": category, "key": key}
        )
        
        if existing:
            return await self._apply_update_policy(existing, value, confidence)
        else:
            return await self._create_memory(user_id, category, key, value, confidence, source_session_id)
```

---

## 5. Memory Update Policy

### 5.1 Update Rules

```python
class MemoryUpdatePolicy:
    
    async def apply(
        self,
        existing: MemoryItem,
        new_value: str,
        new_confidence: float
    ) -> MemoryItem:
        
        # Rule 1: User-set memories — NEVER overwrite without user action
        if existing.is_user_set:
            # Chỉ log attempt, không update
            await log_blocked_update(existing.id, new_value, reason="user_set_protection")
            return existing
        
        # Rule 2: User-confirmed memories — only update if new confidence > 0.9
        if existing.is_user_confirmed and new_confidence < 0.9:
            return existing
        
        # Rule 3: PREFERENCE category — OVERWRITE only if higher confidence
        if existing.category == MemoryCategory.PREFERENCE:
            if new_confidence > existing.confidence:
                return await self._overwrite(existing, new_value, new_confidence)
            return existing
        
        # Rule 4: HEALTH_GOAL — APPEND if different, OVERWRITE if refinement
        if existing.category == MemoryCategory.HEALTH_GOAL:
            if self._is_refinement(existing.value, new_value):
                return await self._overwrite(existing, new_value, new_confidence)
            else:
                return await self._append(existing, new_value, new_confidence)
        
        # Rule 5: CONTEXTUAL — always OVERWRITE (context is time-sensitive)
        if existing.category == MemoryCategory.CONTEXTUAL:
            return await self._overwrite(existing, new_value, new_confidence)
        
        # Default: MERGE
        return await self._merge(existing, new_value, new_confidence)
```

### 5.2 Conflict Resolution

```python
class ConflictResolver:
    
    async def resolve(
        self,
        memory: MemoryItem,
        conflicting_value: str,
        context: dict
    ) -> MemoryItem:
        """
        Khi có conflicting information:
        
        Example: Memory says "preferred_address: anh"
                 But user just said "hãy gọi mình là bạn nhé"
        """
        
        # Rule: explicit user correction → ALWAYS wins
        if self._is_explicit_user_correction(conflicting_value, context):
            updated = await update_memory(
                memory.id,
                value=conflicting_value,
                is_user_confirmed=True,
                times_confirmed=memory.times_confirmed + 1
            )
            return updated
        
        # Rule: version conflict (same session edited twice)
        if self._is_version_conflict(memory, context):
            # Keep newer value
            return await update_memory(memory.id, value=conflicting_value)
        
        # Default: keep existing, increment conflict_count
        await increment_conflict_count(memory.id)
        return memory
```

---

## 6. Memory Expiration

```python
MEMORY_TTL_CONFIG = {
    MemoryCategory.PREFERENCE: {
        "tier": "long",
        "expires_days": None,  # Permanent
        "refresh_on_access": False,  # Không cần refresh
    },
    MemoryCategory.HEALTH_GOAL: {
        "tier": "medium",
        "expires_days": 90,
        "refresh_on_access": True,  # Reset TTL khi truy cập
    },
    MemoryCategory.INTERACTION: {
        "tier": "medium",
        "expires_days": 30,
        "refresh_on_access": True,
    },
    MemoryCategory.CONTEXTUAL: {
        "tier": "medium",
        "expires_days": 7,           # Context ngắn hạn
        "refresh_on_access": False,  # Context không refresh
    },
    MemoryCategory.MEDICAL_PREFERENCE: {
        "tier": "long",
        "expires_days": None,
        "refresh_on_access": False,
    },
}

# Background job chạy hàng ngày
async def expire_memories():
    await db.execute("""
        UPDATE memory_items 
        SET status = 'expired'
        WHERE expires_at IS NOT NULL 
          AND expires_at < NOW()
          AND status = 'active'
    """)
    
    # Hard delete memories expired > 7 days
    await db.execute("""
        DELETE FROM memory_items
        WHERE status = 'expired'
          AND expires_at < NOW() - INTERVAL '7 days'
    """)
```

---

## 7. Memory Prompt Injection

### 7.1 Injection Format

```python
async def build_memory_prompt_block(
    user_id: str,
    context: dict,
    current_query: str
) -> str:
    
    memories = await get_top_k_memories(
        user_id=user_id,
        context=context,
        query=current_query,
        k=8
    )
    
    if not memories:
        return ""
    
    # Group by category
    grouped = group_by_category(memories)
    
    lines = ["## Những điều Meto nhớ về anh/chị\n"]
    
    if MemoryCategory.PREFERENCE in grouped:
        lines.append("**Phong cách giao tiếp:**")
        for m in grouped[MemoryCategory.PREFERENCE]:
            lines.append(f"- {sanitize_for_prompt(m.key)}: {sanitize_for_prompt(m.value)}")
    
    if MemoryCategory.HEALTH_GOAL in grouped:
        lines.append("\n**Mục tiêu sức khỏe:**")
        for m in grouped[MemoryCategory.HEALTH_GOAL]:
            lines.append(f"- {sanitize_for_prompt(m.value)}")
    
    if MemoryCategory.CONTEXTUAL in grouped:
        lines.append("\n**Gần đây:**")
        for m in grouped[MemoryCategory.CONTEXTUAL]:
            lines.append(f"- {sanitize_for_prompt(m.value)}")
    
    lines.append("\n*Dùng những thông tin này để cá nhân hóa câu trả lời. Không đề cập trực tiếp "
                 "rằng bạn 'nhớ' điều này trừ khi user hỏi.*")
    
    return "\n".join(lines)
```

### 7.2 Prompt Injection Prevention

```python
class MemorySanitizer:
    """
    Ngăn prompt injection qua memory values.
    Memory values được extract từ user conversations —
    một user có thể cố inject thông qua chat.
    """
    
    # Patterns nguy hiểm
    DANGEROUS_PATTERNS = [
        r"ignore previous instructions",
        r"you are now",
        r"system prompt",
        r"forget everything",
        r"\bact as\b",
        r"\bpretend\b",
        r"</s>|<\|im_end\|>|<\|endoftext\|>",  # Token manipulation
        r"\[\[.*\]\]",  # Potential injection syntax
        r"<system>|<\|system\|>",
    ]
    
    def sanitize(self, value: str) -> str:
        """
        1. Strip dangerous patterns
        2. Escape special characters
        3. Truncate to max length
        """
        # Check patterns
        value_lower = value.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, value_lower):
                # Log security event
                logger.warning(f"Memory injection attempt detected: {value[:100]}")
                return "[nội dung không hợp lệ]"
        
        # Truncate
        max_length = 200
        if len(value) > max_length:
            value = value[:max_length] + "..."
        
        # Escape special characters that could affect prompt structure
        value = value.replace("##", "")   # No headers
        value = value.replace("```", "")  # No code blocks
        
        return value
    
    def sanitize_key(self, key: str) -> str:
        """Ensure key is safe snake_case"""
        return re.sub(r"[^a-z0-9_]", "", key.lower())[:50]
```

### 7.3 Hallucination Prevention

```python
class MemoryHallucinationGuard:
    """
    Ngăn Meto "nhớ" những điều không thực sự được lưu.
    """
    
    MIN_CONFIDENCE_FOR_INJECTION = 0.7
    MIN_TIMES_CONFIRMED_FOR_HEALTH_CLAIMS = 2
    
    def should_inject(self, memory: MemoryItem, context: dict) -> bool:
        
        # Too low confidence → don't inject
        if memory.confidence < self.MIN_CONFIDENCE_FOR_INJECTION:
            return False
        
        # Health-related memories need more confirmation
        if (memory.category == MemoryCategory.HEALTH_GOAL and 
            memory.times_confirmed < self.MIN_TIMES_CONFIRMED_FOR_HEALTH_CLAIMS and
            not memory.is_user_set):
            return False
        
        # Contextual memories: check not too old relative to their TTL
        if memory.category == MemoryCategory.CONTEXTUAL:
            age_days = (utcnow() - memory.created_at).days
            if age_days > 3:  # Contextual memories stale after 3 days
                return False
        
        return True
    
    def tag_with_source(self, memory: MemoryItem) -> str:
        """
        Tag memory với source metadata để AI model biết nguồn gốc.
        AI có thể dùng tag này để calibrate confidence.
        """
        if memory.is_user_set:
            return f"[USER_CONFIRMED] {memory.value}"
        elif memory.times_confirmed >= 3:
            return f"[VERIFIED] {memory.value}"
        elif memory.confidence >= 0.9:
            return f"[HIGH_CONFIDENCE] {memory.value}"
        else:
            return f"[INFERRED] {memory.value}"
```

---

## 8. User-Editable Memories

### 8.1 User-facing API

```python
# app/api/memory.py

@router.get("/memory/items")
async def list_memories(
    category: MemoryCategory | None = None,
    current_user: User = Depends(get_current_user)
) -> MemoryListResponse:
    """User xem danh sách memories của mình"""
    
    memories = await db.fetch("""
        SELECT id, category, key, value, 
               is_user_set, is_user_confirmed,
               created_at, updated_at, last_accessed_at,
               expires_at
        FROM memory_items
        WHERE user_id = :user_id
          AND status = 'active'
          AND (expires_at IS NULL OR expires_at > NOW())
          AND (:category IS NULL OR category = :category)
        ORDER BY category, importance_score DESC
    """, {"user_id": current_user.id, "category": category})
    
    return MemoryListResponse(
        items=[MemoryItemPublic.from_db(m) for m in memories],
        total=len(memories)
    )

@router.put("/memory/items/{memory_id}")
async def update_memory(
    memory_id: str,
    update: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user)
) -> MemoryItemPublic:
    """User sửa một memory"""
    
    memory = await get_memory(memory_id, current_user.id)
    
    # Sanitize user input
    safe_value = MemorySanitizer().sanitize(update.value)
    
    updated = await db.fetch_one("""
        UPDATE memory_items 
        SET value = :value,
            is_user_confirmed = true,
            is_user_set = true,
            times_confirmed = times_confirmed + 1,
            updated_at = NOW()
        WHERE id = :id AND user_id = :user_id
        RETURNING *
    """, {"value": safe_value, "id": memory_id, "user_id": current_user.id})
    
    return MemoryItemPublic.from_db(updated)

@router.delete("/memory/items/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user)
) -> dict:
    """User xóa một memory"""
    
    await db.execute("""
        UPDATE memory_items 
        SET status = 'deleted', deleted_at = NOW()
        WHERE id = :id AND user_id = :user_id
    """, {"id": memory_id, "user_id": current_user.id})
    
    return {"success": True}

@router.delete("/memory/all")
async def clear_all_memories(
    current_user: User = Depends(get_current_user)
) -> dict:
    """User xóa toàn bộ memories"""
    
    count = await db.execute("""
        UPDATE memory_items 
        SET status = 'deleted', deleted_at = NOW()
        WHERE user_id = :user_id AND status = 'active'
    """, {"user_id": current_user.id})
    
    # Clear Redis cache
    await redis.delete(f"memory:cache:{current_user.id}")
    
    # Audit log
    await audit_log(current_user.id, "all_memories_cleared", {"count": count})
    
    return {"success": True, "deleted_count": count}
```

### 8.2 Memory UI (Settings Screen)

```
Settings → Meto AI → Bộ nhớ của tôi

┌──────────────────────────────────────────────────────────┐
│  🧠 Bộ nhớ Meto                                          │
│  Meto nhớ những điều này để giúp anh/chị tốt hơn        │
│                                                          │
│  [Phong cách giao tiếp]                                  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Cách xưng hô    │ "anh"                     [Sửa] │  │
│  │ Phong cách      │ "Giải thích đơn giản"     [Sửa] │  │
│  │ Độ dài trả lời  │ "Ngắn gọn"               [Sửa] │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Mục tiêu sức khỏe]                                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Mục tiêu chính  │ "Kiểm soát đường huyết"  [Sửa] │  │
│  │ Lo lắng         │ "Biến chứng thận"         [Sửa] │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Ngữ cảnh gần đây]                                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Đang theo dõi HbA1c                          [Xóa] │  │
│  │ Lịch khám 5/7/2026                           [Xóa] │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Xóa toàn bộ bộ nhớ Meto] ← destructive, confirm     │
└──────────────────────────────────────────────────────────┘
```

---

## 9. Consent Model

### 9.1 Per-category Consent

```python
class MemoryConsentSettings(BaseModel):
    user_id: str
    
    # Per-category opt-in
    preference_memory_enabled: bool = True      # Default ON
    health_goal_memory_enabled: bool = True     # Default ON
    interaction_memory_enabled: bool = True     # Default ON
    contextual_memory_enabled: bool = False     # Default OFF (most sensitive)
    medical_preference_memory_enabled: bool = True  # Default ON
    
    # Cross-session memory (master switch)
    cross_session_memory_enabled: bool = True   # Default ON
    
    updated_at: datetime
```

### 9.2 Memory Collection Gate

```python
async def should_collect_memory(
    category: MemoryCategory,
    user_id: str
) -> bool:
    consent = await get_memory_consent(user_id)
    
    if not consent.cross_session_memory_enabled:
        return False
    
    CONSENT_MAP = {
        MemoryCategory.PREFERENCE: consent.preference_memory_enabled,
        MemoryCategory.HEALTH_GOAL: consent.health_goal_memory_enabled,
        MemoryCategory.INTERACTION: consent.interaction_memory_enabled,
        MemoryCategory.CONTEXTUAL: consent.contextual_memory_enabled,
        MemoryCategory.MEDICAL_PREFERENCE: consent.medical_preference_memory_enabled,
    }
    
    return CONSENT_MAP.get(category, False)
```

---

## 10. Privacy Model

### 10.1 Encryption

```python
# Memory values được encrypt at rest
class MemoryEncryption:
    """
    AES-256-GCM encryption cho memory values.
    Key management: Azure Key Vault.
    Key per user (không phải shared key).
    """
    
    async def encrypt_value(self, user_id: str, plain_value: str) -> str:
        key = await key_vault.get_user_memory_key(user_id)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plain_value.encode())
        return base64.b64encode(cipher.nonce + tag + ciphertext).decode()
    
    async def decrypt_value(self, user_id: str, encrypted_value: str) -> str:
        key = await key_vault.get_user_memory_key(user_id)
        data = base64.b64decode(encrypted_value)
        nonce, tag, ciphertext = data[:16], data[16:32], data[32:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
```

### 10.2 Cross-user Isolation

```python
# Memory queries LUÔN có WHERE user_id filter
# RLS policy tại PostgreSQL layer (xem 04_SAFETY_PRIVACY.md)

ALTER TABLE memory_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY memory_user_isolation ON memory_items
    USING (user_id = current_setting('app.current_user_id')::uuid);
```

---

## 11. Storage Schema

```sql
CREATE TABLE memory_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Content
    category            TEXT NOT NULL,
    key                 TEXT NOT NULL,
    value               TEXT NOT NULL,      -- Encrypted at rest
    
    -- Scoring
    relevance_score     FLOAT NOT NULL DEFAULT 0.5,
    recency_score       FLOAT NOT NULL DEFAULT 1.0,
    importance_score    FLOAT NOT NULL DEFAULT 0.5,
    composite_score     FLOAT NOT NULL DEFAULT 0.5,
    
    -- Confidence & verification
    confidence          FLOAT NOT NULL DEFAULT 0.7,
    times_confirmed     INTEGER NOT NULL DEFAULT 0,
    is_user_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
    is_user_set         BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Tier & lifecycle
    tier                TEXT NOT NULL DEFAULT 'medium',  -- 'short' | 'medium' | 'long'
    status              TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'expired' | 'deleted'
    
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ,        -- NULL = never expires
    deleted_at          TIMESTAMPTZ,
    
    -- Source
    source_session_id   TEXT,
    
    -- Conflict tracking
    conflict_count      INTEGER NOT NULL DEFAULT 0,
    
    CONSTRAINT unique_user_category_key UNIQUE (user_id, category, key),
    CONSTRAINT valid_category CHECK (
        category IN ('preference', 'health_goal', 'interaction', 'contextual', 'medical_preference')
    ),
    CONSTRAINT valid_tier CHECK (tier IN ('short', 'medium', 'long')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'expired', 'deleted'))
);

-- Indexes
CREATE INDEX idx_memory_user_category ON memory_items(user_id, category, status);
CREATE INDEX idx_memory_expiry ON memory_items(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_memory_score ON memory_items(user_id, composite_score DESC);
CREATE INDEX idx_memory_accessed ON memory_items(user_id, last_accessed_at DESC);
```

---

## 12. Memory Audit Log

```sql
CREATE TABLE memory_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    memory_id       UUID REFERENCES memory_items(id),
    
    action          TEXT NOT NULL,
    -- 'created' | 'updated' | 'accessed' | 'deleted' | 'blocked_update' | 'injection_attempt'
    
    category        TEXT,
    key_name        TEXT,           -- Key name (không phải value)
    actor           TEXT NOT NULL,  -- 'system' | 'user' | 'memory_collector'
    
    details         JSONB,          -- Additional context (no sensitive values)
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_memory_audit_user ON memory_audit_logs(user_id, created_at);
```

---

## 13. Memory System Flow — End to End

```
SESSION STARTS
    │
    ▼
┌──────────────────────────────────────────┐
│  MEMORY RETRIEVAL (per request)          │
│                                          │
│  1. get_top_k_memories(user_id, context) │
│  2. Filter by consent & confidence       │
│  3. Score: relevance + recency + import  │
│  4. Top 8 memories selected              │
│  5. Sanitize (injection prevention)      │
│  6. Build memory_prompt_block            │
└──────────────────────────────────────────┘
    │ injected into prompt
    ▼
AI MODEL PROCESSES (with memory context)
    │
    ▼
USER ↔ METO EXCHANGE (multiple turns)
    │
    ▼
SESSION ENDS (SOFT_CLOSED)
    │
    ▼
┌──────────────────────────────────────────┐
│  MEMORY COLLECTION (post-session)        │
│                                          │
│  1. Extract memories via AI              │
│  2. Filter by confidence >= 0.7          │
│  3. Sanitize values                      │
│  4. Check consent per category           │
│  5. Upsert with update policy            │
│  6. Recompute scores                     │
│  7. Encrypt & store                      │
└──────────────────────────────────────────┘
```

---

## 14. Acceptance Criteria

### AC-MEM-001: Memory Tiers
- [ ] Short-term memory lives in Redis, TTL = session lifetime
- [ ] Medium-term memory expires after 30 days (refreshable)
- [ ] Long-term memory (PREFERENCE, MEDICAL_PREFERENCE) never expires
- [ ] CONTEXTUAL memory expires after 7 days, not refreshable

### AC-MEM-002: Scoring & Retrieval
- [ ] Top-K retrieval returns max 8 memories
- [ ] Composite score formula: 0.40*relevance + 0.35*recency + 0.25*importance
- [ ] No more than 3 memories from same category in top-K
- [ ] Memory accessed → last_accessed_at updated

### AC-MEM-003: Collection
- [ ] Memory extraction runs after session SOFT_CLOSED
- [ ] Only memories with confidence >= 0.7 are stored
- [ ] Consent checked per category before storing
- [ ] Extraction does not store raw health values (labs, metrics, medications)

### AC-MEM-004: Injection Safety
- [ ] Dangerous patterns blocked: injection attempts logged + memory rejected
- [ ] Memory values truncated to 200 characters
- [ ] Memory keys sanitized to snake_case max 50 chars
- [ ] User-set memories never overwritten by automated extraction

### AC-MEM-005: User Control
- [ ] User can view all memories categorized via Settings
- [ ] User can edit any memory → immediately reflected in next session
- [ ] User can delete individual memory or all memories
- [ ] Clear all memories → cleared within 1 second
- [ ] Memory consent toggles work independently per category

### AC-MEM-006: Privacy
- [ ] Memory values encrypted at rest (AES-256-GCM)
- [ ] Cross-user memory access returns 0 results (RLS enforced)
- [ ] Memory audit log records all create/update/delete actions
- [ ] Injection attempts logged as security events

### AC-MEM-007: Expiration
- [ ] Background job runs daily, expires memories past TTL
- [ ] Hard delete runs 7 days after soft expiry
- [ ] User account deletion triggers cascade memory deletion

---

*Xem thêm: 08_CONVERSATION_ENGINE.md (khi nào memory được inject vào prompt), 04_SAFETY_PRIVACY.md (consent model), 09_TOOLS_AND_ACTIONS.md (tool results có thể trigger memory updates)*
