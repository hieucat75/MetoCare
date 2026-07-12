# MetoCare Medication — Architecture Decision Index

**Maintained by:** PTH / OpenClaw  
**Architecture Baseline:** `medication-architecture-v1.0`  
**Last Updated:** 2026-07-11  

> **Governance rule:** This index is the canonical reference for all ADR status.
> When an ADR is superseded, update `Superseded By` here AND in the ADR file itself.
> New ADRs are numbered sequentially from ADR-13 onward.
> Never edit the body of an Accepted ADR — create a superseding ADR instead.

---

## Active ADRs

| ADR | Title | Status | Gate | Domain | Arch Version | Supersedes | Superseded By |
|-----|-------|--------|------|--------|-------------|------------|---------------|
| [ADR-01](ADR-01-MEDICATION-KNOWLEDGE-STRUCTURE.md) | Medication Knowledge Structure | ✅ Accepted | Gate 1 | Knowledge | v1.0 | — | — |
| [ADR-02](ADR-02-DRUG-INTERACTION-ENGINE.md) | Drug Interaction Engine | 🔵 Accepted (Gate 2) | Gate 2 | Interaction | v1.0 | — | — |
| [ADR-03](ADR-03-MEDICATION-HISTORY-AND-TIMELINE.md) | Medication History & Timeline | ✅ Accepted | Gate 1 | History & Audit | v1.0 | — | — |
| [ADR-04](ADR-04-MEDICATION-RECONCILIATION.md) | Medication Reconciliation | ✅ Accepted | Gate 1 | Reconciliation | v1.0 | — | — |
| [ADR-05](ADR-05-OCR-MEDICATION-PIPELINE.md) | OCR Medication Pipeline | 🟡 Proposed | Gate 3 | OCR | v1.0 | — | — |
| [ADR-06](ADR-06-TRADITIONAL-MEDICINE-AND-SUPPLEMENTS.md) | Traditional Medicine & Supplements | 🟡 Proposed | Gate 3 | Taxonomy | v1.0 | — | — |
| [ADR-07](ADR-07-AI-KNOWLEDGE-SOURCE.md) | AI Knowledge Source | 🟡 Proposed | Gate 3 | AI | v1.0 | — | — |
| [ADR-08](ADR-08-ALLERGY-AND-CROSS-REACTIVITY.md) | Allergy & Cross-Reactivity | 🔵 Proposed (Gate 2) | Gate 2 | Safety | v1.0 | — | — |
| [ADR-09](ADR-09-CLINICAL-DECISION-SUPPORT-PLACEMENT.md) | CDS Placement | ✅ Accepted | Gate 1 | CDS | v1.0 | — | — |
| [ADR-10](ADR-10-DRUG-KNOWLEDGE-DATA-SOURCES.md) | Drug Knowledge Data Sources | 🔵 Proposed (Gate 2) | Gate 2 | Data Sources | v1.0 | — | — |
| [ADR-11](ADR-11-MEDICATION-LIFECYCLE.md) | Medication Lifecycle | ✅ Accepted | Gate 1 | Lifecycle | v1.0 | — | — |
| [ADR-12](ADR-12-PHI-PRIVACY-AND-ENCRYPTION.md) | PHI, Privacy & Encryption | 🔵 Proposed (Gate 2) | Gate 2 | Privacy | v1.0 | — | — |

**Legend:**
- ✅ Accepted — Gate approved by PTH. Implementation may proceed.
- 🔵 Accepted/Proposed (Gate N) — Architecture decision made; implementation requires Gate N approval.
- 🟡 Proposed — Decision pending PTH approval.
- 🔴 Superseded — Replaced by a newer ADR. Do not implement.
- ⬛ Deprecated — No longer relevant.

---

## Superseded ADRs

*None at v1.0.*

| ADR | Title | Superseded By | Date Superseded | Reason |
|-----|-------|--------------|-----------------|--------|
| — | — | — | — | — |

---

## Gate Status

| Gate | ADRs | Status | Unblocks |
|------|------|--------|---------|
| **Gate 1** | ADR-01, 03, 04, 09, 11 | ✅ All approved (2026-07-11) | P0 implementation |
| **Gate 2** | ADR-02, 08, 10, 12 | 🔵 Pending PTH approval | P3: interaction, allergy, production launch |
| **Gate 3** | ADR-05, 06, 07 | 🟡 Pending design + PTH approval | P2–P4: OCR, AI, traditional medicine |

---

## Open Decisions Tracker

| # | Question | Blocks | Status |
|---|----------|--------|--------|
| OQ-1 | Expired medication re-review flow | P0 | ✅ Resolved 2026-07-11 — statement-first |
| OQ-2 | MIMS Vietnam licensing (~$15–50K/year) | Gate 2 | ⏳ Pending PTH |
| OQ-3 | DrugBank Open commercial license | Gate 2 | ⏳ Pending PTH |
| OQ-4 | WHO ATC commercial use approval | Gate 2 | ⏳ Pending PTH |
| OQ-5 | LLM provider DPA for health data | Gate 3 | ⏳ Pending PTH |
| OQ-6 | Vietnamese data deletion vs anonymization policy | Gate 2 | ⏳ Pending PTH |
| OQ-7 | Designated Vietnamese clinical advisor (identity) | Gate 1 sign-offs | ⏳ Pending PTH |

---

## How to Add a New ADR

1. Number sequentially: next available is **ADR-13**.
2. Copy [ADR template](#adr-template) below.
3. Fill in `Supersedes` if replacing an existing decision.
4. Update the superseded ADR: set `Superseded By: ADR-XX` in its metadata block.
5. Update this index: add row to Active ADRs, move superseded ADR to Superseded table.
6. Submit for PTH approval before implementation.
7. Do NOT edit the body of the superseded ADR — its history is immutable.

---

## ADR Template

```markdown
# ADR-XX — [Title]

**Status:** PROPOSED — Gate N  
**Date:** YYYY-MM-DD  
**Deciders:** PTH, [roles]

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-XX |
| Status | Proposed |
| Architecture Version | medication-architecture-vN.N |
| Implementation Gate | Gate N |
| Domain | [Domain] |
| Supersedes | ADR-YY (if applicable) |
| Superseded By | None |

---

## Context

[Why this decision is needed]

## Problem

[What problem this solves]

## Options Considered

### Option A — ...
### Option B — ...

## Trade-off Table

| Criterion | A | B |
|-----------|---|---|

## Recommended Decision

[Decision + rationale]

## Consequences

[Schema, API, service layer impact]

## Approval Required From

- [ ] PTH
- [ ] [Other roles]

## Implementation Gate

Gate N — [what this blocks or unblocks]
```

---

## Architecture Versions

| Version | Tag | Date | Key Changes |
|---------|-----|------|-------------|
| v1.0 | `medication-architecture-v1.0` | 2026-07-11 | Gate 1 approved. ADR-01/03/04/09/11 signed. P0 Implementation Plan v1.1. |
