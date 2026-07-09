"""c1_m05: extend audit_logs with details (structured before/after)

Additive ALTER on `audit_logs` (BR-M05-02: "Mọi thay đổi giá ghi audit
(người, thời điểm, giá cũ→mới)" — every price change must be audited with
actor, time, and old→new price). The existing `AuditLog`/`audit.record()`
had no field to carry structured before/after values; `resource_id` is
explicitly documented as a bare reference id, never a content field.

`details` is nullable JSON, no FK, no index — same bare-value convention as
`resource_id`/`actor_id`/`clinic_id` (append-only log intentionally has no
referential dependency on entities that may later be pruned/archived).
PHI-free by the same discipline as the rest of `AuditLog`: reference ids and
business-rule values only (e.g. `{"old_price": ..., "new_price": ...}`),
never note/lab/diagnosis content — enforced by convention at each call site,
not by the column itself.

Reusable by later C1 milestones needing the same before/after capture (e.g.
M07 appointment reschedule, M10 invoice discount/refund) — written once,
generically, rather than per-milestone.

Revision ID: c1_m05_audit_details
Revises: c1_m05_service_fields
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1_m05_audit_details"
down_revision = "c1_m05_service_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "details")
