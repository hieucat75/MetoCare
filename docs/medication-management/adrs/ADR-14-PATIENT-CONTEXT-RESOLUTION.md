# ADR-14 — Patient Context Resolution

**Status:** PROPOSED — approved in principle (PTH, 2026-07-15); remains formally Proposed until K4, but the architectural boundary (Context ≠ CDS) is binding starting now — no code from K1 onward may conflate the two. Gate 2 for execution (data-dependent on ADR-02 interaction content); boundary decision itself is Gate 1-level and adopted immediately.
**Date:** 2026-07-15 (PTH review round 1: approved in principle, acceptance deferred to K4)
**Deciders:** PTH (product), Tech Lead, Clinical Advisor

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-14 |
| Status | Proposed |
| Architecture Version | medication-architecture-v1.1 |
| Implementation Gate | Gate 2 (execution) / Gate 1 (architectural boundary) |
| Domain | Personalization / Context |
| Supersedes | None |
| Superseded By | None |

---

## Context

ADR-01 makes Knowledge drug-centric: a fact about metformin is true for every patient taking metformin, independent of who they are. ADR-02 (Drug Interaction Engine) and the K5 Clinical Decision Support phase are write-time safety alerting: when a medication is added, the engine evaluates it against the patient's existing medications and, if a rule matches, persists a `medication_alerts` row.

PTH's K0 review identified a third, currently-unmodeled layer sitting between these two: **read-time personalization**. Example from the review — a patient viewing the Levothyroxine detail page who is separately taking Calcium should see *"Bạn đang dùng Calcium. Nên uống cách Levothyroxine tối thiểu 4 giờ."* rendered directly on the Knowledge cards, not only as a separate alert generated when Calcium was first added.

PTH was explicit that this must not be folded into either existing layer: *"Knowledge không nên trộn Context. Context Engine khác Interaction Engine. Đó là USP của MetoCare."*

## Problem

Without an explicit architectural boundary for this layer:

1. Engineers implementing personalization later have no obvious home for it — the natural shortcut is to bolt patient-specific logic onto the Knowledge API route handler or, worse, onto the frontend, which breaks the "Knowledge is impersonal, patient-neutral" invariant ADR-01 establishes.
2. Conflating this with CDS/K5 risks two failure modes: (a) treating a low-stakes informational note with the same governance weight as a persisted safety alert (over-engineering, slows down useful UX), or (b) treating a genuine safety alert as a soft, best-effort "tip" that can silently fail to render (under-engineering, a real safety gap).
3. Resolving "what should this patient see about this drug" requires reading across bounded contexts that don't currently share a service layer: Medication (active drug list), Labs/Metrics, and — once it exists — Allergy (ADR-08). Without a named service boundary, this cross-context read logic gets duplicated or scattered.
4. Personalization must still obey the "no AI-generated clinical facts" invariant (ADR-07, and repeatedly emphasized by PTH). A Context Engine that free-text-generates sentences is exactly the hallucination risk this whole initiative exists to prevent — it must be a deterministic *filter and template* over already-approved content (per ADR-13's `status='approved'` rows), never a generator.

## Options Considered

### Option A — No separate layer; Context = call the CDS/K5 engine at read time and reuse its output verbatim
Whatever CDS computed and persisted at write-time is simply displayed again at read-time.

### Option B — Context Engine as a distinct, synchronous, read-scoped domain service
A new `app/domain/context/` module: reads the patient's active medications/labs/allergies (read-only), filters the same `drug_interactions`/`drug_monitoring` rows CDS uses down to ones relevant to "this drug, given what else this patient is on," and returns ephemeral `contextual_notes` attached to the Knowledge API response. Never persists, never creates `medication_alerts`.

### Option C — Bake personalization directly into the Knowledge API endpoint's SQL query
No separate service; the `GET /medications/{id}/knowledge` handler joins across patient medications inline.

### Option D — AI layer synthesizes the personalized sentence at render time
Rejected outright — violates the standing "AI must never generate clinical facts" constraint (ADR-07, and PTH's explicit instruction in this session).

---

## Trade-off Table

| Criterion | A (reuse CDS output) | B (distinct read-time service) | C (inline in API handler) | D (AI-generated) |
|-----------|----------------------|----------------------------------|----------------------------|-------------------|
| Preserves CDS as authoritative, must-not-miss safety layer | ❌ Conflates severity tiers | ✅ Yes — CDS stays the only alert-of-record | ⚠️ Ambiguous | ❌ N/A |
| Low-stakes info can be shown without alert-grade governance overhead | ❌ No — everything inherits alert weight | ✅ Yes | ⚠️ Ambiguous | — |
| Testable / auditable as its own unit | ⚠️ Coupled to CDS internals | ✅ Isolated service, own tests | ❌ Buried in route handler | — |
| Reusable across Knowledge API and future surfaces (e.g. AI explain-tool) | ⚠️ Limited | ✅ Yes | ❌ No | — |
| Risk of clinical hallucination | ✅ None (structured only) | ✅ None (structured only, template-filled) | ✅ None | ❌ Rejected |
| Matches "Knowledge stays patient-neutral" invariant from ADR-01 | ⚠️ Blurs it | ✅ Keeps Knowledge and Context cleanly separated | ❌ Blurs it | — |

---

## Recommended Decision

**Option B — Context Engine as a distinct, synchronous, read-scoped domain service, architecturally separate from CDS/K5.**

## Why This Option

The core distinction PTH is pointing at is real and load-bearing: **CDS is the safety net (write-time, persisted, must not have false negatives); Context is the concierge (read-time, ephemeral, optimizes for helpful, best-effort personalization)**. A missed CDS alert is a safety incident. A missed contextual note is a UX gap — acceptable, because the safety-critical version of the same fact was already caught by CDS at write-time. Keeping them as two services with two different risk tolerances lets each be built, tested, and governed at the rigor it actually needs, instead of forcing informational tips through alert-grade review overhead, or letting alert-grade content slip through best-effort rendering.

Both engines are allowed to read the *same* underlying `drug_interactions` rows (per ADR-02) — the separation is about **trigger, persistence, and severity handling**, not about maintaining two copies of clinical content.

## Consequences

**New service:** `app/domain/context/` — read-only, no new tables required at K0/K1. Reads:
- Patient's active medications (existing `Medication` rows, `lifecycle_status='active'`)
- Patient's relevant lab values (existing metrics tables)
- Patient's allergy list (once ADR-08 lands — until then, this input is simply empty, not blocking)
- `drug_interactions` / `drug_monitoring` rows scoped to `status='approved'` (per ADR-13)

**API impact:** `GET /patients/{id}/medications/{id}/knowledge` response gains an optional field:
```
"contextual_notes": [
  {
    "trigger": "active_medication" | "lab_value" | "allergy",
    "related_to": "string",          -- e.g. "Calcium"
    "note": "string",                -- template-filled from drug_interactions.patient_message, never freehand
    "source_interaction_id": "uuid"  -- traceable back to the approved rule that produced it
  }
]
```
Every note must trace back to an `approved` row via `source_interaction_id` — there is no path for this field to contain content that didn't go through ADR-13's review lifecycle.

**Boundary rule with CDS:** if the underlying rule's `severity` is `contraindicated` or `major`, the Context Engine does not restate it as a standalone soft note — it defers to the CDS alert (links to it, or is suppressed in favor of it) to avoid two systems describing the same risk in different tones. Only `moderate`/`minor` severity rules, plus purely informational (non-interaction) notes, render as `contextual_notes`.

**Explicitly NOT in scope for this ADR:** the allergy data model (ADR-08 owns that), the CDS alert persistence model (ADR-09/ADR-02 own that), and any AI involvement (explicitly excluded per Option D above).

## Roadmap Placement

Per PTH's revised roadmap: **K4 — Context Engine**, positioned after K1–K3 (Knowledge Repository → Clinical Review → API → Companion Integration) and before or alongside **K5 — Interaction/CDS**. Context Engine's MVP can run against whatever `drug_interactions` content already exists at K4 — it does not require ADR-02's full rule set to be complete, only for what exists to be `approved`.

## Approval Required From

- [ ] PTH — confirms Context Engine and CDS remain architecturally separate services, not merged for convenience later
- [ ] Clinical Advisor — confirms the severity-based deferral rule (Context defers to CDS for `contraindicated`/`major`) is clinically sound
- [ ] Tech Lead — confirms cross-bounded-context read access (Medication + Labs + future Allergy) is acceptable as a read-only service dependency, not a tighter coupling

## Implementation Gate

**Gate 1 for the architectural boundary** (this ADR's decision — Context ≠ CDS — should be adopted now, at K0, so no future code conflates them). **Gate 2 for execution**, since meaningful `contextual_notes` output depends on `drug_interactions` content existing, which is gated behind ADR-02/Gate 2 same as K5.
