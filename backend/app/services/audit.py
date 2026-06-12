"""Audit service — append-only logging of access/actions on patient data.

Security_Compliance_Framework + Data_Model_Overview §4.5. Never stores sensitive
content, only metadata (who/what/when/outcome).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.governance import AuditLog


def record(
    db: Session,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    outcome: str = "success",
    ip_address: str | None = None,
    device: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        ip_address=ip_address,
        device=device,
    )
    db.add(entry)
    db.flush()  # assign id without committing the surrounding transaction
    return entry
