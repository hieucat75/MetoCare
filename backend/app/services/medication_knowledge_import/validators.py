"""Business-rule validation beyond schema.py's structural typing.

Pure functions — no database access (that's provenance.py) — over an
already-parsed schema.KnowledgeFile. Returns a list of error strings rather
than raising on the first problem, so one import attempt reports everything
wrong at once (matches K1-S2's own "validate everything before writing
anything" convention).

Most of the spec's validation rules are already enforced structurally by
schema.py's Pydantic models (ai_generated must literally be False,
disclaimer.acknowledged must literally be True, references must be a
non-empty list with a url or document_identifier, locale is a fixed
Literal). This module covers what schema.py cannot express as a type:
the specialty-code controlled vocabulary (see
docs/medication-management/MEDICATION_PHASE_A_BLOCKING_FINDINGS.md
Finding 2 for why this is a hardcoded allowlist, not a DB lookup, at the
A1a layer) and duplicate-reference detection within one file.
"""

from __future__ import annotations

from app.services.medication_knowledge_import.schema import KnowledgeFile

# PTH's explicit minimum controlled vocabulary (2026-07-16) — not the full
# medical specialty taxonomy. clinical_specialties has zero seeded DB rows
# today (Finding 2); this allowlist lets A1a validate file *structure*
# without depending on that seed existing yet. provenance.py performs the
# separate DB-existence check once the seed lands.
ALLOWED_SPECIALTY_CODES = frozenset(
    {
        "clinical_pharmacy",
        "internal_medicine",
        "endocrinology",
        "cardiology",
        "nephrology",
        "gastroenterology",
        "hematology",
    }
)


def validate_business_rules(knowledge_file: KnowledgeFile) -> list[str]:
    """Return every business-rule violation found, or an empty list if none."""
    errors: list[str] = []
    errors.extend(_validate_specialty_codes(knowledge_file))
    errors.extend(_validate_no_duplicate_references(knowledge_file))
    return errors


def _validate_specialty_codes(knowledge_file: KnowledgeFile) -> list[str]:
    errors = []
    for code in knowledge_file.review_metadata.specialty_codes:
        if code not in ALLOWED_SPECIALTY_CODES:
            errors.append(
                f"invalid specialty code {code!r} — not in the controlled "
                f"vocabulary {sorted(ALLOWED_SPECIALTY_CODES)}"
            )
    return errors


def _validate_no_duplicate_references(knowledge_file: KnowledgeFile) -> list[str]:
    """A file citing the same document twice (same publisher+title+
    publication_date) is almost certainly an authoring mistake, not a
    real double-citation."""
    seen: set[tuple[str, str, str]] = set()
    errors = []
    for ref in knowledge_file.references:
        key = (ref.publisher, ref.title, ref.publication_date.isoformat())
        if key in seen:
            errors.append(
                f"duplicate reference in the same file: publisher={ref.publisher!r}, "
                f"title={ref.title!r}, publication_date={ref.publication_date}"
            )
        seen.add(key)
    return errors
