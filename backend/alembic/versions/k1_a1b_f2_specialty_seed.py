"""K1-A1B-F2: seed the clinical_specialties controlled vocabulary.

Resolves Finding 2 (Phase A blocking findings) — approved by PTH
2026-07-16. `clinical_specialties` was structurally created by K1-M01 but
has never been seeded. A1a's own "invalid specialty code" validation rule
needs something real to validate against; this data-only migration seeds
PTH's specified minimum 7-code controlled vocabulary.

Data-only, idempotent (INSERT ... WHERE NOT EXISTS, keyed on the existing
uq_clinical_specialties_code unique constraint), no new tables or columns
— matches this repo's t9_m2_drug_seed precedent for data-only migrations.

Explicitly does NOT assign any specific person/reviewer identity to any
specialty — that's a separate, later governance decision (K1.5+), not
part of this seed.

No clinical content is authored by this migration. No API route, no
frontend, no AI wiring touches this — same dormancy discipline as every
other K1 migration.

Revision ID: k1_a1b_f2_specialty_seed
Revises: k1_a1b_f1_schema_complete
Create Date: 2026-07-16
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1_a1b_f2_specialty_seed"
down_revision: str | None = "k1_a1b_f1_schema_complete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# PTH's explicit minimum vocabulary (2026-07-16) — not the full medical
# specialty taxonomy. (code, display_name_vi, display_name_en).
SPECIALTIES: list[tuple[str, str, str]] = [
    ("clinical_pharmacy", "Dược lâm sàng", "Clinical Pharmacy"),
    ("internal_medicine", "Nội khoa", "Internal Medicine"),
    ("endocrinology", "Nội tiết", "Endocrinology"),
    ("cardiology", "Tim mạch", "Cardiology"),
    ("nephrology", "Thận học", "Nephrology"),
    ("gastroenterology", "Tiêu hóa", "Gastroenterology"),
    ("hematology", "Huyết học", "Hematology"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, name_vi, name_en in SPECIALTIES:
        existing = conn.execute(
            sa.text("SELECT id FROM clinical_specialties WHERE code = :code"),
            {"code": code},
        ).fetchone()
        if existing is not None:
            # Idempotent: re-running this migration (or a future re-run of
            # the same seed data) never inserts a duplicate row.
            continue
        conn.execute(
            sa.text(
                "INSERT INTO clinical_specialties "
                "(id, code, display_name_vi, display_name_en, is_active) "
                "VALUES (:id, :code, :name_vi, :name_en, true)"
            ),
            {
                "id": str(uuid.uuid4()),
                "code": code,
                "name_vi": name_vi,
                "name_en": name_en,
            },
        )


def downgrade() -> None:
    """Remove exactly the 7 seeded codes — never a blanket DELETE, in case
    a future PR seeds additional specialties before this one is rolled
    back (fails closed rather than guessing which rows are "ours")."""
    conn = op.get_bind()
    codes = [code for code, _, _ in SPECIALTIES]
    placeholders = ", ".join(f":code_{i}" for i in range(len(codes)))
    params = {f"code_{i}": code for i, code in enumerate(codes)}
    conn.execute(
        sa.text(f"DELETE FROM clinical_specialties WHERE code IN ({placeholders})"),
        params,
    )
