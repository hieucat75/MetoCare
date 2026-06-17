"""DoctorCarePlanService — manages the doctor approval and lifecycle of CarePlans.

See app/models/care.py for C2 status-machine and validates details.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.care import CarePlan, CarePlanStatus, Doctor
from app.services import audit


class DoctorCarePlanService:
    def __init__(self, db: Session):
        self.db = db

    def approve(
        self,
        care_plan_id: str,
        doctor: Doctor,
        approved_at: dt.datetime | None = None,
    ) -> CarePlan:
        """Transition status to APPROVED. Only DOCTOR.

        Uses direct SQL UPDATE to bypass ORM validator hook.
        """
        plan = self.db.get(CarePlan, care_plan_id)
        if plan is None or plan.deleted_at is not None:
            raise ValueError(f"CarePlan {care_plan_id} not found.")

        if plan.status in (CarePlanStatus.APPROVED, CarePlanStatus.ARCHIVED):
            raise ValueError(f"Cannot approve care plan in {plan.status} status.")

        now = approved_at or utcnow()

        self.db.execute(
            update(CarePlan)
            .where(CarePlan.id == care_plan_id)
            .values(
                status=CarePlanStatus.APPROVED,
                approved_by_doctor_id=doctor.id,
                approved_at=now,
            )
        )
        self.db.flush()

        audit.record(
            self.db,
            actor_type="doctor",
            actor_id=doctor.user_id,
            action="care_plan.approve",
            resource_type="care_plan",
            resource_id=care_plan_id,
            outcome="success",
            severity="info",
        )

        return plan
