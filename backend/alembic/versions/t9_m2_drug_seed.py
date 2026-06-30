"""t9_m2: seed the drug_catalog reference table

t9_m1 created the empty drug_catalog table; the autocomplete endpoint
(GET /medications/suggest) therefore returned zero results on any environment
that had not been seeded out-of-band (staging included). This one-time data
migration populates the reference catalog from the canonical in-code seed list.
Idempotent — entries already present (keyed on lowercase generic_name) are
skipped, so re-running is harmless.

Revision ID: t9_m2_drug_seed
Revises: t9_m1_drug_cat
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

revision: str = "t9_m2_drug_seed"
down_revision: str | None = "t9_m1_drug_cat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Import lazily and reuse the exact idempotent seed used by the tests so the
    # catalog never drifts between code, tests, and the deployed database.
    from app.services.drug_catalog import seed_catalog

    bind = op.get_bind()
    session = Session(bind=bind)
    inserted = seed_catalog(session)
    print(f"[t9_m2_drug_seed] inserted {inserted} drug_catalog rows")


def downgrade() -> None:
    # Reseedable reference data — clearing all rows is the inverse of the seed.
    op.execute("DELETE FROM drug_catalog")
