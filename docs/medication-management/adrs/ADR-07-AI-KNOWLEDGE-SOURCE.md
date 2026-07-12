# ADR-07 — AI Knowledge Source

**Status:** PROPOSED — Gate 3 (expansion — but principles must be set before AI features ship)  
**Date:** 2026-07-11  
**Deciders:** PTH, Clinical Advisor, Tech Lead

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-07 |
| Status | Proposed |
| Architecture Version | medication-architecture-v1.0 |
| Implementation Gate | Gate 3 |
| Domain | AI Knowledge Source |
| Supersedes | None |
| Superseded By | None |

---


## Context

Meto AI hiện nhận medication list dưới dạng text (name, dose, frequency) và generates responses based on LLM training data. Không có knowledge grounding mechanism.

Vấn đề: AI có thể nói điều gì đó về Metformin mà không trace về bất kỳ verified source nào. Nếu AI sai về clinical fact — đây là patient safety risk.

---

## Problem

Nếu user hỏi "Metformin và rượu có sao không?" và AI trả lời từ training data:
- Câu trả lời có thể đúng, có thể sai, có thể outdated
- Không thể audit sau này để biết AI đã dùng data gì
- Không thể cập nhật behavior khi clinical guidelines thay đổi
- Không thể detect hallucination

**Non-negotiable principle:** AI KHÔNG ĐƯỢC là nguồn sự thật lâm sàng. AI CHỈ ĐƯỢC giải thích/trình bày dữ liệu đã được kiểm chứng.

---

## Decision Drivers

- AI hallucination của clinical facts là unacceptable
- All AI drug statements must be traceable to a specific knowledge source
- Knowledge must be updateable independently of model
- AI can assist extraction, matching, candidate suggestion — but cannot be authoritative
- Vietnamese localization: knowledge must be relevant to VN patient population and MoH guidelines
- Must work within current infrastructure (no new ML pipeline needed)

---

## Options Considered

### Option A — LLM training data only (current state)
AI uses its own knowledge. Fast. No grounding. Hallucination risk.

### Option B — Drug catalog as context injection
Inject full drug_catalog entries into AI prompt for referenced drugs. AI "explains" from this data.

### Option C — Retrieval-Augmented Generation (RAG) over knowledge base
Build drug knowledge vector store. AI retrieves relevant knowledge at query time.

### Option D — Tool-based knowledge retrieval
AI calls `get_drug_knowledge(drug_id)` tool → gets structured knowledge from DB → uses in response.

### Option E — Hybrid: structured context injection + knowledge tools
For known drugs (in catalog): inject knowledge from DB.  
For unknown drugs: AI flags uncertainty explicitly, does NOT generate clinical facts.

---

## Trade-off Table

| Criterion | A (training data) | B (catalog injection) | C (RAG) | D (tools) | E (hybrid) |
|-----------|------------------|----------------------|---------|-----------|------------|
| Hallucination prevention | ❌ None | ✅ Good for catalog drugs | ✅ Good | ✅ Good | ✅ Good |
| Handles unknown drugs | ⚠️ Hallucination risk | ❌ No data | ⚠️ Limited | ❌ Returns empty | ✅ Graceful fallback |
| Infrastructure needed | ✅ None | ✅ None | ❌ Vector DB | ⚠️ Tool impl | ⚠️ Tool impl |
| Knowledge update | ❌ Retrain | ✅ Update DB | ✅ Update DB | ✅ Update DB | ✅ Update DB |
| Response latency | ✅ Fast | ⚠️ Slightly more tokens | ❌ Slow | ⚠️ One extra DB call | ⚠️ Acceptable |
| Auditability | ❌ None | ✅ Source is DB row | ✅ | ✅ | ✅ |
| Implementation complexity | ✅ Zero | ✅ Low | ❌ High | ⚠️ Medium | ⚠️ Medium |

---

## Recommended Decision

**Option E — Hybrid: structured knowledge injection for known drugs + explicit uncertainty for unknown drugs.**

RAG (Option C) is over-engineered for this use case. A vector database adds operational complexity without meaningful benefit over direct DB queries for a catalog of <1000 drugs.

Tool-based (Option D) alone requires AI to decide when to call the tool — risk of AI skipping it and falling back to training data. Hybrid is safer: inject relevant knowledge automatically from the medications in context.

---

## Why This Option

For MetoCare's scale (< 1000 drugs in catalog, 5–10 medications per patient in context), the entire drug knowledge for a patient's medication list fits in a prompt. No RAG needed.

For drugs NOT in catalog: AI must say explicitly "Tôi không có thông tin đã kiểm chứng về thuốc này trong danh mục MetoCare. Hỏi dược sĩ hoặc bác sĩ của bạn." This is better than hallucinating.

---

## Consequences

**Knowledge injection in AI context (enhanced `_build_medications()`):**
```python
def _build_medications_with_knowledge(db, user_id) -> dict:
    medications = fetch_active_medications(user_id)
    result = []
    for med in medications:
        entry = {
            "name": med.name,
            "generic_name": med.generic_name,
            "drug_class": med.drug_class,
            "dose": med.dose_text,
            "frequency": med.frequency,
            "status": med.status,
            "medication_category": med.medication_category,
        }
        # Inject knowledge if catalog-linked
        if med.drug_product_id:
            knowledge = fetch_drug_knowledge(med.drug_product_id)
            entry["knowledge"] = {
                "common_use": knowledge.common_indications[:2],      # max 2
                "caution_summary": knowledge.caution_flags[:2],      # max 2, not full list
                "requires_monitoring": knowledge.monitoring_key,     # e.g., "eGFR every 6 months"
                "evidence_note": None  # for prescription drugs
            }
        else:
            entry["knowledge"] = None  # AI must not fabricate
            entry["knowledge_missing"] = True

        result.append(entry)

    return {
        "medications": result,
        "active_alerts_count": fetch_active_alert_count(user_id),
        "note": "knowledge=null means no verified data available for this drug"
    }
```

**AI system prompt additions:**
```
MEDICATION KNOWLEDGE RULES:
- medication.knowledge is the ONLY authoritative source for drug facts
- If medication.knowledge is null or knowledge_missing=true:
    Do NOT provide clinical information about this drug from your training data
    Say: "Tôi không có thông tin đã kiểm chứng về [drug_name] trong hệ thống MetoCare.
          Vui lòng hỏi dược sĩ hoặc bác sĩ của bạn."
- If medication.knowledge is present:
    You MAY explain common_use and caution_summary in plain Vietnamese
    You MUST cite "theo thông tin trong danh mục thuốc MetoCare"
    You MUST NOT add clinical information beyond what is in knowledge
- NEVER generate interaction warnings from your training data
  Interaction warnings come ONLY from active_alerts_count > 0 prompt context
- NEVER recommend dose adjustments, even if you "know" standard doses
```

**AI tool set for medication domain:**
```
get_drug_interaction_explanation(alert_id) 
  → Returns: mechanism_detail, clinical_effect, management from drug_interactions table
  → AI uses this to explain an existing alert in plain Vietnamese
  → AI does NOT generate the alert — it only explains one that already exists

get_adherence_summary(patient_id, days=30)
  → Returns: adherence metrics for AI to reference
  → AI uses for adherence coaching

get_medication_timeline(patient_id, from_date, to_date)
  → Returns: medication events for AI to reference in temporal questions
```

**Evidence citation format in AI responses:**
```
"Theo thông tin trong danh mục thuốc MetoCare (cập nhật [source_version]):
Metformin thuộc nhóm Biguanide, thường được dùng để điều trị tiểu đường type 2 bằng cách giảm sản xuất glucose tại gan.

Lưu ý: cần theo dõi chức năng thận định kỳ khi dùng thuốc này."
```

**Fallback behavior when knowledge is missing:**
```
"Tôi không tìm thấy thông tin đã được kiểm chứng về [drug_name] trong danh mục thuốc MetoCare.
Hỏi dược sĩ hoặc bác sĩ của bạn để biết thêm về thuốc này."
```

NOT: "Based on my knowledge, [drug_name] is used for..." — này là hallucination path.

**Knowledge update lifecycle:**
1. Drug knowledge updated in `drug_ingredient_knowledge` table
2. `source_version` bumped
3. AI context immediately reflects new data (no model retraining)
4. Prompt includes source_version for auditability: "Thông tin cập nhật theo phiên bản [X]"

---

## Data Model Impact

- `drug_ingredient_knowledge` table (ADR-01) is the knowledge source
- `drug_interactions` table (ADR-02) is the interaction source for AI tool
- No new tables needed — AI reads from existing knowledge layer

---

## API Impact

- `GET /ai/drug-knowledge/{drug_product_id}` — internal AI tool endpoint (not public)
- `GET /ai/interaction-explanation/{alert_id}` — internal AI tool endpoint

---

## Security and Privacy Impact

- AI tools are internal-only — no external exposure
- AI tool responses must not contain other patients' data
- PHI in AI prompt: medication data is patient-scoped, already enforced in context builder
- LLM provider must not train on prompt content — confirm DPA (same concern as ADR-05)

---

## Clinical Safety Impact

This ADR directly addresses the hallucination risk. Without it:
- AI can confidently state wrong drug information
- No mechanism to update AI behavior without model retraining
- Cannot audit "what did AI tell patient X about drug Y on date Z"

With this ADR:
- AI facts are traceable to knowledge_version
- Drugs without knowledge get explicit "I don't know" response
- Knowledge update is a data operation, not a model operation

---

## Migration Impact

None. Enhancement to context builder. No schema changes required in P0 (knowledge layer built in ADR-01/P1+).

---

## Operational Ownership

- Clinical Advisor owns `drug_ingredient_knowledge` content
- Tech team owns AI tool implementation
- Monthly review: are any patients asking about drugs NOT in catalog? → expand catalog

---

## Open Questions

1. **Token budget:** Full knowledge for 8 medications in context = ~600 tokens. Current budget is 300. Accept increased cost or implement selective knowledge injection? **[Tech Lead evaluates with PTH on API cost impact]**
2. **Interaction explanation tool:** Should AI be able to call `get_drug_interaction_explanation()` on its own, or should the explanation be pre-computed and injected? **[Tech Lead architecture decision]**

---

## Approval Required From

- [ ] PTH — principle: "AI cannot cite clinical facts from training data" (non-negotiable, but explicit sign-off needed)
- [ ] PTH — token budget increase acceptance
- [ ] Clinical Advisor — review of knowledge injection format

## Implementation Gate

**Gate 3 — does not block P0.**  
BUT: must be implemented before any medication explanation feature ships. If `explain_medication` AI feature is in P1, this ADR must be implemented in P1.
