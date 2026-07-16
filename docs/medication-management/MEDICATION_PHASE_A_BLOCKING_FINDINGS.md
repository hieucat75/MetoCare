# Medication Knowledge — Phase A Blocking Findings

**Date:** 2026-07-16
**Status:** Open — tracked separately per PTH's explicit instruction, not resolved by weakening provenance or bypassing validation.
**Related:** `MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md`

Two findings from PR-A1 planning that block **A1b** (persistence), not A1a (loader/validation, no DB writes). Both must be resolved via their own small, explicit changes — not by dropping requirements or silently bypassing checks.

---

## Finding 1 — Structured reference persistence (schema gap, blocks A1b)

### Problem

ADR-13's schema has no `drug_references` table and no `references` column on any of the 5 knowledge tables — only a single `source: VARCHAR(255)` string per row. The original Phase A plan proposed keeping the full reference list only in the versioned YAML source file, with the DB holding just a short summary string.

**PTH rejected this.** Reasons (verbatim from PTH's review):
- A future patient-facing API needs to return sources to patients.
- Reviewers need to know what document a piece of content is based on.
- A monthly content-update pipeline needs to compare source/version over time.
- Source files can be renamed, moved, or lost — provenance that lives only there is not durable.
- One knowledge item can be based on multiple documents.
- One document can back multiple knowledge items (many-to-many, not 1:1).

A single `VARCHAR(255)` cannot represent any of this. Storing `source="curated:metocare-v1"` (or similar) loses real provenance from the repository.

### Required resolution

- A structured, queryable relation for references — either:
  - a `drug_references` table (one row per distinct reference document) + a join table associating references with rows across the 5 knowledge tables (polymorphic association, same pattern ADR-13 already uses for `knowledge_review_specialties` — a `knowledge_table` + `knowledge_row_id` pair, since references span all 5 tables without one physical FK target), or
  - an equivalent structure achieving the same many-to-many query capability — exact shape is an implementation decision for whoever writes the migration, not fixed by this finding.
- Minimum fields per reference (PTH's spec): `publisher`, `title`/citation, `source_type`, `url` or a document identifier, `publication_date`, `source_version`, `accessed_at`.
- Every knowledge item must be linkable to **at least one** structured reference — not optional, not a free-text fallback.
- This requires a real Alembic migration. Per ADR-13's own convention (schema enforces invariants, not authorship) and this project's ADR discipline, adding two new tables to an already-Accepted ADR's domain is an **extension of ADR-13's existing schema**, not a new architectural decision — recommend treating it as a small addendum PR (`K1-A1-pre — add drug_references + knowledge_reference_links tables`) requiring Codex + compliance + architecture review before merge, same bar as any K1 migration, but not requiring a new ADR document (no new architectural *decision* is being made — the shape is dictated by the existing polymorphic-association pattern already Accepted in ADR-13).

### Status

🔴 **Not started.** A1a proceeds without this (it only validates the `references:` field's structure in the input file — that validation is correct regardless of where persistence eventually lands). **A1b must not begin persisting knowledge content until this migration exists and the orchestrator writes real reference rows** — not a placeholder, not a re-serialization into the existing `source` string.

---

## Finding 2 — `clinical_specialties` seed data (blocks A1b integration tests)

### Problem

`clinical_specialties` is structurally created (K1-M01 migration) but has zero seeded rows anywhere in the codebase — confirmed by grep across migrations and seed scripts. A1a's "invalid specialty code" validation rule (required by the original Phase A spec) needs something real to validate against. With an empty table, the only two naive options are both wrong: reject every specialty reference unconditionally (makes the check useless — it can never pass), or silently skip/bypass the check when the table is empty (defeats the purpose of having it).

### Required resolution

Seed a minimal controlled vocabulary before A1b's integration tests run. PTH's specified minimum list (7 codes, not the full medical specialty taxonomy):

```
clinical_pharmacy
internal_medicine
endocrinology
cardiology
nephrology
gastroenterology
hematology
```

Requirements per PTH:
- Data only — no migration needed (`clinical_specialties` table and its `uq_clinical_specialties_code` constraint already exist).
- Must be idempotent (safe to run more than once — matches this codebase's existing seed-script convention, e.g. `drug_catalog` seeding).
- Seeds **specialty codes only** — does not assign or imply any specific person/reviewer identity.

### Status

🟡 **Not started.** A1a's validator can and should implement the *structural* half of this check now — a hardcoded Python-level allowlist of the 7 codes above, requiring no DB access — so file-shape validation works immediately. The *DB-existence* half (in `provenance.py`, confirming a referenced code actually has a `clinical_specialties` row) can be coded in A1a too, but its integration test cannot meaningfully pass until this seed exists — that test is written and marked pending real seed data, not skipped or weakened. **Recommend the seed script land as part of, or immediately before, A1b** (small enough to bundle, but tracked here as its own explicit prerequisite so it isn't silently forgotten).

---

## Audit output requested by PTH — Calcium salt identity (informational, feeds a future separate PR)

Not a Phase A finding (Phase B blocker only, tracked in the main plan doc), but PTH asked the agent to audit and propose an identity structure rather than leave it open-ended.

**Audit:** the 41-entry catalog seed (`backend/app/services/drug_catalog.py`) has zero entries with `generic_name` containing "calcium" in any form. The existing ingredient-dedup convention (K1-S2 migration, `drug_ingredients.name_inn` uniqueness) already keys on verbatim salt-form INN strings — e.g. `insulin aspart` and `insulin glargine` are separate ingredient rows, never collapsed to a generic `insulin`. A generic `"Calcium"` ingredient would break that existing convention, and clinically the salts differ meaningfully (absorption, GI tolerance, elemental calcium content, and — most relevant to Phase B's own Levothyroxine↔Calcium interaction note — timing guidance can differ by formulation).

**Proposal (for the future `K1-S2b` PR, not built here):**
- Add distinct `drug_ingredients` rows for the specific salts actually relevant to Phase B's content: `calcium carbonate`, `calcium citrate` at minimum (the two most common OTC/supplement forms in the Vietnamese market context this product targets); add `calcium acetate` only if Phase B's authored content actually needs it (it's primarily a renal/phosphate-binder use case, less likely relevant to a general patient-education monitoring page).
- Group them under a shared `drug_classes` parent (e.g. a `"calcium_supplements"` class) so Phase B's Levothyroxine↔Calcium interaction note can reference the class-level relationship ("separate timing from calcium-containing supplements generally") while still keeping each salt's own page/ingredient identity distinct for anything salt-specific.
- Whoever writes `K1-S2b` should confirm this grouping against real product data (Vietnamese OTC calcium product formulations) before finalizing — this audit is a starting proposal, not a clinical determination.
