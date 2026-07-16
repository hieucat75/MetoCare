"""Medication Knowledge Import Framework — Phase A (PR-A1).

Tooling to validate structured YAML/JSON knowledge authoring files before
they can ever be persisted as draft rows in the ADR-13 knowledge tables.

Scope lock (PTH, Phase A GO): this package (A1a slice) never writes to the
database and never authors clinical content. `loader.py` and `schema.py`
parse and structurally validate an input file; `validators.py` applies
business rules (controlled vocabulary, forbidden AI-generated content);
`provenance.py` resolves medication identity against the existing
relational core (read-only). Persistence (`orchestrator.py`, calling
`app.services.knowledge_repository.create_draft`) is A1b, and is blocked
until the structured-reference-persistence schema gap is resolved — see
docs/medication-management/MEDICATION_PHASE_A_BLOCKING_FINDINGS.md.

No API route, no frontend, no AI wiring touches this package.
"""

from __future__ import annotations
