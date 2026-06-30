"""Meto AI — Context Builder.

Assembles the 9 context blocks from the database for a given user + screen.
Implements 02_CONTEXT_ENGINE.md specification:
- Consent gating (no consent → block excluded)
- Per-screen relevance (Dashboard vs Labs vs Medications etc.)
- Token budget enforcement
- Graceful degradation (missing data → None, not hallucinated)
- Context isolation (all queries parameterized with user_id)

DB call ordering:
  All DB queries are ALWAYS called in a fixed order regardless of consent or screen,
  to ensure stable behavior (tests and real DB both benefit from predictable sequencing):
  1. user_profile (execute #1)
  2. health_summary (execute #2)
  3. care_plan (execute #3)
  4. care_tasks (execute #4) — always queried (plan_id="__none__" if no plan)
  5. medications (execute #5)
  6. recent_labs (execute #6)
  7. recent_metrics (execute #7)
  8. appointments (execute #8)
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.context.schemas import AssembledContext, ScreenContext
from app.models.meto import MetoConsent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screen → blocks mapping (02_CONTEXT_ENGINE.md §2)
# "always" = include if data + consent present (key blocks for this screen)
# "conditional" = include if data present + consent present
# ---------------------------------------------------------------------------

_SCREEN_BLOCKS: dict[str, set[str]] = {
    "dashboard": {"user_profile", "health_summary", "care_plan", "medications", "recent_metrics", "today_context"},
    "labs": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "recent_metrics", "today_context"},
    "medications": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "today_context"},
    "metrics": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "recent_metrics", "today_context"},
    "nutrition": {"user_profile", "health_summary", "medications", "recent_labs", "recent_metrics", "today_context"},
    "care_plan": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "recent_metrics", "today_context"},
    "profile": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "recent_metrics", "today_context"},
}

_DEFAULT_SCREEN_BLOCKS: set[str] = {
    "user_profile", "health_summary", "care_plan", "medications",
    "recent_labs", "recent_metrics", "today_context",
}

# Consent keys required per block
_BLOCK_CONSENT: dict[str, str] = {
    "health_summary": "health_data",
    "care_plan": "care_plan",
    "medications": "medications",
    "recent_labs": "labs",
    "recent_metrics": "metrics",
    "today_context": "care_plan",  # today context is gated by care_plan consent
}

# Approximate token budget per block
_TOKEN_BUDGET: dict[str, int] = {
    "user_profile": 150,
    "health_summary": 300,
    "care_plan": 250,
    "medications": 300,
    "recent_labs": 350,
    "recent_metrics": 250,
    "screen_context": 100,
    "today_context": 200,
    "safety_flags": 100,
}

_LABS_LOOKBACK_DAYS = 90
_METRICS_LOOKBACK_DAYS = 30
_MAX_LABS = 10
_MAX_METRICS_TYPES = 5
_MAX_MEDICATIONS = 10


class ContextBuilder:
    """Assemble context blocks for a Meto chat request.

    All DB queries are parameterized with user_id and called in a FIXED order
    regardless of consent/screen, then filtered based on consent and screen config.
    """

    def build(
        self,
        db: Session,
        user_id: str,
        screen_context: ScreenContext,
    ) -> AssembledContext:
        """Build the full assembled context for a chat request."""
        screen_id = screen_context.screen_id or "dashboard"
        screen_blocks = _SCREEN_BLOCKS.get(screen_id, _DEFAULT_SCREEN_BLOCKS)

        # 1. Load consent state
        consents = self._load_consents(db, user_id)

        included_blocks: list[str] = []
        missing_consents: list[str] = []
        total_tokens = 0

        # ---------------------------------------------------------------
        # Fixed DB call order: queries happen regardless of consent/screen
        # Results are gated afterwards.
        # ---------------------------------------------------------------

        # DB call #1: user profile
        raw_user_profile = self._build_user_profile(db, user_id)

        # DB call #2: health summary
        raw_health_summary = self._build_health_summary(db, user_id)

        # DB calls #3+#4: care plan + tasks (always called together)
        raw_care_plan = self._build_care_plan(db, user_id)

        # DB call #5: medications
        raw_medications = self._build_medications(db, user_id)

        # DB call #6: recent labs
        raw_recent_labs = self._build_recent_labs(db, user_id)

        # DB call #7: recent metrics
        raw_recent_metrics = self._build_recent_metrics(db, user_id)

        # DB call #8: appointments (for today_context)
        raw_today_context = self._build_today_context(db, user_id)

        # ---------------------------------------------------------------
        # Now apply consent + screen gating
        # ---------------------------------------------------------------

        # user_profile — no consent required
        user_profile = None
        if raw_user_profile:
            user_profile = raw_user_profile
            included_blocks.append("user_profile")
            total_tokens += _TOKEN_BUDGET["user_profile"]

        # health_summary
        health_summary = None
        if "health_summary" in screen_blocks:
            if consents.get("health_data"):
                health_summary = raw_health_summary
                if health_summary:
                    included_blocks.append("health_summary")
                    total_tokens += _TOKEN_BUDGET["health_summary"]
            else:
                missing_consents.append("health_data")

        # care_plan
        care_plan = None
        if "care_plan" in screen_blocks:
            if consents.get("care_plan"):
                care_plan = raw_care_plan
                if care_plan:
                    included_blocks.append("care_plan")
                    total_tokens += _TOKEN_BUDGET["care_plan"]
            else:
                if "care_plan" not in missing_consents:
                    missing_consents.append("care_plan")

        # medications
        medications = None
        if "medications" in screen_blocks:
            if consents.get("medications"):
                medications = raw_medications
                if medications:
                    included_blocks.append("medications")
                    total_tokens += _TOKEN_BUDGET["medications"]
            else:
                if "medications" not in missing_consents:
                    missing_consents.append("medications")

        # recent_labs
        recent_labs = None
        if "recent_labs" in screen_blocks:
            if consents.get("labs"):
                recent_labs = raw_recent_labs
                if recent_labs:
                    included_blocks.append("recent_labs")
                    total_tokens += _TOKEN_BUDGET["recent_labs"]
            else:
                if "labs" not in missing_consents:
                    missing_consents.append("labs")

        # recent_metrics
        recent_metrics = None
        if "recent_metrics" in screen_blocks:
            if consents.get("metrics"):
                recent_metrics = raw_recent_metrics
                if recent_metrics:
                    included_blocks.append("recent_metrics")
                    total_tokens += _TOKEN_BUDGET["recent_metrics"]
            else:
                if "metrics" not in missing_consents:
                    missing_consents.append("metrics")

        # screen context — always, no consent needed
        screen_ctx = self._build_screen_context(screen_context)
        included_blocks.append("screen_context")
        total_tokens += _TOKEN_BUDGET["screen_context"]

        # today_context — include if care_plan or medications consent
        today_ctx: dict = {}
        if "today_context" in screen_blocks:
            if consents.get("care_plan") or consents.get("medications"):
                today_ctx = raw_today_context
                included_blocks.append("today_context")
                total_tokens += _TOKEN_BUDGET["today_context"]

        # safety_flags — always computed from already-fetched data
        safety_flags = self._build_safety_flags(db, user_id, recent_labs, recent_metrics)
        if safety_flags:
            included_blocks.append("safety_flags")
        total_tokens += _TOKEN_BUDGET["safety_flags"]

        return AssembledContext(
            user_profile=user_profile,
            health_summary=health_summary,
            care_plan=care_plan,
            medications=medications,
            recent_labs=recent_labs,
            recent_metrics=recent_metrics,
            screen_context=screen_ctx,
            today_context=today_ctx,
            safety_flags=safety_flags,
            total_estimated_tokens=total_tokens,
            missing_consents=missing_consents,
            included_blocks=included_blocks,
        )

    # -----------------------------------------------------------------------
    # Consent loading
    # -----------------------------------------------------------------------

    def _load_consents(self, db: Session, user_id: str) -> dict[str, bool]:
        """Load all consent records for user. Returns {context_type: True}."""
        rows = (
            db.query(MetoConsent)
            .filter(
                MetoConsent.user_id == user_id,
                MetoConsent.granted.is_(True),
                MetoConsent.revoked_at.is_(None),
            )
            .all()
        )
        return {row.context_type: True for row in rows}

    def _check_consent(self, db: Session, user_id: str, context_type: str) -> bool:
        row = (
            db.query(MetoConsent)
            .filter(
                MetoConsent.user_id == user_id,
                MetoConsent.context_type == context_type,
                MetoConsent.granted.is_(True),
                MetoConsent.revoked_at.is_(None),
            )
            .first()
        )
        return row is not None

    # -----------------------------------------------------------------------
    # Block builders — each consumes exactly ONE db.execute() call
    # (except care_plan which consumes TWO: plan + tasks)
    # -----------------------------------------------------------------------

    def _build_user_profile(self, db: Session, user_id: str) -> dict | None:
        """Build user profile block. Consumes DB execute #1."""
        try:
            row = db.execute(
                text("""
                    SELECT u.full_name, pp.date_of_birth, pp.gender,
                           pp.preferred_address
                    FROM users u
                    LEFT JOIN patient_profiles pp ON pp.user_id = u.id
                    WHERE u.id = :uid AND u.is_active = 1
                    LIMIT 1
                """),
                {"uid": user_id},
            ).fetchone()

            if not row:
                return None

            dob = row[1]
            age = None
            if dob:
                try:
                    if isinstance(dob, str):
                        dob_dt = dt.date.fromisoformat(dob[:10])
                    elif isinstance(dob, dt.date):
                        dob_dt = dob
                    else:
                        dob_dt = None
                    if dob_dt:
                        today = dt.date.today()
                        age = today.year - dob_dt.year - (
                            (today.month, today.day) < (dob_dt.month, dob_dt.day)
                        )
                except Exception:
                    age = None

            return {
                "display_name": row[0] or "Người dùng",
                "age": age,
                "gender": row[2] or "unknown",
                "preferred_address": row[3] or "bạn",
                "language": "vi",
                "account_type": "patient",
            }
        except Exception as exc:
            logger.warning("Error building user_profile for %s: %s", user_id, exc)
            return None

    def _build_health_summary(self, db: Session, user_id: str) -> dict | None:
        """Build health summary block. Consumes DB execute #2."""
        try:
            row = db.execute(
                text("""
                    SELECT primary_conditions, secondary_conditions,
                           allergies, blood_type, chronic_conditions
                    FROM patient_profiles
                    WHERE user_id = :uid
                    LIMIT 1
                """),
                {"uid": user_id},
            ).fetchone()

            if not row:
                return None

            def _parse_list(val: Any) -> list:
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    import json
                    try:
                        return json.loads(val)
                    except Exception:
                        return [val] if val.strip() else []
                return []

            return {
                "primary_conditions": _parse_list(row[0]),
                "secondary_conditions": _parse_list(row[1]),
                "allergies": _parse_list(row[2]),
                "blood_type": row[3],
                "chronic_conditions": _parse_list(row[4]),
            }
        except Exception as exc:
            logger.warning("Error building health_summary for %s: %s", user_id, exc)
            return None

    def _build_care_plan(self, db: Session, user_id: str) -> dict | None:
        """Build care plan block. Consumes DB execute #3 (plan) + #4 (tasks).

        Always makes BOTH queries to maintain stable DB call order.
        """
        try:
            plan = db.execute(
                text("""
                    SELECT id, title FROM care_plans
                    WHERE patient_id = :uid AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"uid": user_id},
            ).fetchone()

            today_start = dt.datetime.now(dt.UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            # Always query tasks (stable DB call order)
            plan_id = plan[0] if plan else "__no_plan__"
            tasks = db.execute(
                text("""
                    SELECT title, due_date, status, priority
                    FROM care_tasks
                    WHERE plan_id = :plan_id AND due_date >= :today
                    ORDER BY priority DESC, due_date ASC
                    LIMIT 20
                """),
                {"plan_id": plan_id, "today": today_start},
            ).fetchall()

            if not plan:
                return None

            task_list = []
            for t in tasks:
                task_list.append({
                    "title": t[0],
                    "due_date": str(t[1]) if t[1] else None,
                    "status": t[2] or "pending",
                    "priority": t[3] or "medium",
                })

            completed = sum(1 for t in task_list if t["status"] == "completed")
            return {
                "plan_name": plan[1],
                "active_tasks": task_list[:10],
                "completed_today": completed,
                "total_today": len(task_list),
            }
        except Exception as exc:
            logger.warning("Error building care_plan for %s: %s", user_id, exc)
            return None

    def _build_medications(self, db: Session, user_id: str) -> list | None:
        """Build medications block. Consumes DB execute #5."""
        try:
            rows = db.execute(
                text("""
                    SELECT name, dose, frequency, note, created_at
                    FROM medications
                    WHERE patient_id = :uid AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"uid": user_id, "limit": _MAX_MEDICATIONS},
            ).fetchall()

            if not rows:
                return None

            return [
                {
                    "name": r[0],
                    "dosage": r[1] or "",
                    "frequency": r[2] or "",
                    "note": r[3] or "",
                    "start_date": str(r[4])[:10] if r[4] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Error building medications for %s: %s", user_id, exc)
            return None

    def _build_recent_labs(self, db: Session, user_id: str) -> list | None:
        """Build recent_labs block. Consumes DB execute #6."""
        try:
            cutoff_date = (
                dt.date.today() - dt.timedelta(days=_LABS_LOOKBACK_DAYS)
            ).isoformat()

            rows = db.execute(
                text("""
                    SELECT lr.test_name, lr.value, lr.unit,
                           lr.reference_range, lr.status, lub.test_date
                    FROM lab_results lr
                    JOIN lab_upload_batches lub ON lub.id = lr.batch_id
                    WHERE lub.patient_id = :uid
                      AND lr.deleted_at IS NULL
                      AND lub.deleted_at IS NULL
                      AND (lub.test_date IS NULL OR lub.test_date >= :cutoff_date)
                    ORDER BY lub.test_date DESC, lr.created_at DESC
                    LIMIT :limit
                """),
                {"uid": user_id, "cutoff_date": cutoff_date, "limit": _MAX_LABS},
            ).fetchall()

            if not rows:
                return None

            return [
                {
                    "test_name": r[0],
                    "value": str(r[1]) if r[1] is not None else "",
                    "unit": r[2] or "",
                    "reference_range": r[3] or "",
                    "status": r[4] or "unknown",
                    "collected_date": str(r[5])[:10] if r[5] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Error building recent_labs for %s: %s", user_id, exc)
            return None

    def _build_recent_metrics(self, db: Session, user_id: str) -> list | None:
        """Build recent_metrics block. Consumes DB execute #7."""
        try:
            cutoff = (
                dt.datetime.now(dt.UTC) - dt.timedelta(days=_METRICS_LOOKBACK_DAYS)
            ).isoformat()

            rows = db.execute(
                text("""
                    SELECT metric_type, value, unit, measured_at, status
                    FROM health_metrics
                    WHERE patient_id = :uid
                      AND measured_at >= :cutoff
                      AND deleted_at IS NULL
                    ORDER BY measured_at DESC
                    LIMIT 50
                """),
                {"uid": user_id, "cutoff": cutoff},
            ).fetchall()

            if not rows:
                return None

            # Deduplicate to one entry per metric_type (most recent)
            seen: set[str] = set()
            result = []
            for r in rows:
                metric_type = r[0]
                if metric_type in seen:
                    continue
                seen.add(metric_type)
                result.append({
                    "metric_type": metric_type,
                    "latest_value": str(r[1]) if r[1] is not None else "",
                    "unit": r[2] or "",
                    "measured_at": str(r[3]) if r[3] else None,
                    "status": r[4] or "unknown",
                })
                if len(result) >= _MAX_METRICS_TYPES:
                    break

            return result if result else None
        except Exception as exc:
            logger.warning("Error building recent_metrics for %s: %s", user_id, exc)
            return None

    def _build_screen_context(self, screen_context: ScreenContext) -> dict:
        """Build screen context block — no DB call needed."""
        return {
            "screen_id": screen_context.screen_id or "dashboard",
            "entity_id": screen_context.entity_id,
            "entity_type": screen_context.entity_type,
            "view_context": screen_context.view_context or {},
        }

    def _build_today_context(self, db: Session, user_id: str) -> dict:
        """Build today's context. Consumes DB execute #8."""
        today = dt.date.today().isoformat()
        appointment_list = []

        try:
            appts = db.execute(
                text("""
                    SELECT title, appointment_time, provider_name, location
                    FROM appointments
                    WHERE patient_id = :uid
                      AND date(appointment_time) >= :today
                      AND status != 'cancelled'
                    ORDER BY appointment_time ASC
                    LIMIT 3
                """),
                {"uid": user_id, "today": today},
            ).fetchall()

            appointment_list = [
                {
                    "title": a[0] or "Lịch hẹn",
                    "datetime": str(a[1]) if a[1] else None,
                    "provider": a[2] or "",
                    "location": a[3] or "",
                }
                for a in appts
            ]
        except Exception as exc:
            logger.debug("today_context appointment query failed: %s", exc)

        return {
            "date": today,
            "upcoming_appointments": appointment_list,
        }

    def _build_safety_flags(
        self,
        db: Session,
        user_id: str,
        recent_labs: list | None,
        recent_metrics: list | None,
    ) -> list[str]:
        """Check for critical lab/metric values. No additional DB call."""
        flags: list[str] = []

        if recent_labs:
            for lab in recent_labs:
                if str(lab.get("status", "")).lower() in ("critical", "critical_high", "critical_low"):
                    flags.append(
                        f"⚠️ Giá trị CRITICAL: {lab.get('test_name', '')} = "
                        f"{lab.get('value', '')} {lab.get('unit', '')}"
                    )

        if recent_metrics:
            for metric in recent_metrics:
                if str(metric.get("status", "")).lower() in ("critical", "critical_high", "critical_low"):
                    flags.append(
                        f"⚠️ Chỉ số CRITICAL: {metric.get('metric_type', '')} = "
                        f"{metric.get('latest_value', '')} {metric.get('unit', '')}"
                    )

        return flags
