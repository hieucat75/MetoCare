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
import json
import logging
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.ai.context.schemas import AssembledContext, ScreenContext
from app.models.meto import MetoConsent
from app.models.patient import PatientProfile
from app.models.user import User
from app.utils.number_format import format_lab_display, format_lab_value

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screen → blocks mapping (02_CONTEXT_ENGINE.md §2)
# "always" = include if data + consent present (key blocks for this screen)
# "conditional" = include if data present + consent present
# ---------------------------------------------------------------------------

_SCREEN_BLOCKS: dict[str, set[str]] = {
    "dashboard": {"user_profile", "health_summary", "care_plan", "medications", "recent_labs", "recent_metrics", "today_context"},
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

# Consent keys required per block — kept for reference but NO LONGER used as gate.
# Per product design: T&C covers consent at registration. Meto reads health profile
# by default. Consent management is only in Settings > Quyền riêng tư.
_BLOCK_CONSENT: dict[str, str] = {
    "health_summary": "health_data",
    "care_plan": "care_plan",
    "medications": "medications",
    "recent_labs": "labs",
    "recent_metrics": "metrics",
    "today_context": "care_plan",
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

# Defense-in-depth (AI2): health_metrics has no per-row verified flag, so the AI
# context only trusts metrics from known-confirmed sources — patient-authored
# entries and the lab->metric promotion, which is itself gated on verified lab
# rows upstream (lab.py). Any FUTURE automated writer (e.g. an OCR metric
# extractor) would carry an out-of-list source and is fail-closed excluded from
# Meto until explicitly vetted and added here. NULL source = legacy patient data.
_TRUSTED_METRIC_SOURCES = ("manual", "self_report", "lab_result", "device", "vital")


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

        # Per product design: T&C covers consent at registration.
        # Meto reads health profile by default — no consent gate in chat.
        # Consent management is only in Settings > Quyền riêng tư.
        # _load_consents is retained for Settings endpoints but NOT used here.

        included_blocks: list[str] = []
        missing_consents: list[str] = []  # Always empty — no consent gate in chat
        total_tokens = 0

        # ---------------------------------------------------------------
        # Fixed DB call order: queries happen regardless of consent/screen
        # Results are gated afterwards.
        # ---------------------------------------------------------------

        # Each _build_* method has its own try/except and returns None on failure.
        # The context builder now receives a dedicated session (ctx_db) that is
        # separate from the main request session, so SQL errors here cannot
        # poison the conversation/message writes in the main session.

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
        # Apply screen filtering only — NO consent gating.
        # Per product design: T&C covers consent at registration.
        # All blocks are included if they have data and are relevant to this screen.
        # ---------------------------------------------------------------

        # user_profile — always included (no consent required, always was)
        user_profile = None
        if raw_user_profile:
            user_profile = raw_user_profile
            included_blocks.append("user_profile")
            total_tokens += _TOKEN_BUDGET["user_profile"]

        # health_summary — include if screen uses it and data exists
        health_summary = None
        if "health_summary" in screen_blocks:
            health_summary = raw_health_summary
            if health_summary:
                included_blocks.append("health_summary")
                total_tokens += _TOKEN_BUDGET["health_summary"]

        # care_plan — include if screen uses it and data exists
        care_plan = None
        if "care_plan" in screen_blocks:
            care_plan = raw_care_plan
            if care_plan:
                included_blocks.append("care_plan")
                total_tokens += _TOKEN_BUDGET["care_plan"]

        # medications — include if screen uses it and data exists
        medications = None
        if "medications" in screen_blocks:
            medications = raw_medications
            if medications:
                included_blocks.append("medications")
                total_tokens += _TOKEN_BUDGET["medications"]

        # recent_labs — include if screen uses it and data exists
        recent_labs = None
        if "recent_labs" in screen_blocks:
            recent_labs = raw_recent_labs
            if recent_labs:
                included_blocks.append("recent_labs")
                total_tokens += _TOKEN_BUDGET["recent_labs"]

        # recent_metrics — include if screen uses it and data exists
        recent_metrics = None
        if "recent_metrics" in screen_blocks:
            recent_metrics = raw_recent_metrics
            if recent_metrics:
                included_blocks.append("recent_metrics")
                total_tokens += _TOKEN_BUDGET["recent_metrics"]

        # screen context — always, no consent needed
        screen_ctx = self._build_screen_context(screen_context)
        included_blocks.append("screen_context")
        total_tokens += _TOKEN_BUDGET["screen_context"]

        # today_context — include if screen uses it (no consent gate)
        today_ctx: dict = {}
        if "today_context" in screen_blocks:
            today_ctx = raw_today_context or {}
            if today_ctx:
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
        """Build user profile block. Consumes DB execute #1.

        Uses ORM queries so EncryptedString TypeDecorator auto-decrypts
        full_name and dob before we read them.
        """
        try:
            # ORM query — auto-decrypts EncryptedString fields (full_name)
            user = (
                db.query(User)
                .filter(User.id == user_id, User.is_active.is_(True))
                .first()
            )
            if not user:
                return None

            # ORM query — auto-decrypts EncryptedString fields (dob)
            profile = (
                db.query(PatientProfile)
                .filter(PatientProfile.user_id == user_id)
                .first()
            )

            # full_name: ORM decrypts automatically
            display_name = user.full_name or "Người dùng"

            # Detect residual ciphertext (safety net for rows encrypted before ORM fix)
            if display_name.startswith("gAAAAAB"):
                logger.warning(
                    "user_profile: full_name still looks encrypted for user %s — "
                    "check FIELD_ENCRYPTION_KEY env var",
                    user_id,
                )
                display_name = "Người dùng"

            # dob: ORM decrypts automatically (stored as ISO date string)
            age = None
            if profile and profile.dob:
                try:
                    dob_val = profile.dob
                    birth_year = None
                    if isinstance(dob_val, str) and not dob_val.startswith("gAAAAAB"):
                        birth_year = dt.date.fromisoformat(dob_val[:10]).year
                    elif isinstance(dob_val, dt.date):
                        birth_year = dob_val.year
                    if birth_year is not None:
                        # Vietnamese convention: tuổi = năm hiện tại − năm sinh
                        # (year-based, NOT birthday-precise). Born 1975 → 51 in 2026,
                        # regardless of whether the birthday has passed yet this year.
                        age = dt.date.today().year - birth_year
                except Exception:
                    age = None

            return {
                "display_name": display_name,
                "age": age,
                "gender": (profile.gender if profile else None) or "unknown",
                "preferred_address": "bạn",
                "language": "vi",
                "account_type": "patient",
            }
        except Exception as exc:
            logger.warning("Error building user_profile for %s: %s", user_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_health_summary(self, db: Session, user_id: str) -> dict | None:
        """Build health summary block. Consumes DB execute #2.

        Uses ORM query so EncryptedString TypeDecorator auto-decrypts
        known_conditions and allergies before we read them.
        """
        try:
            # ORM query — auto-decrypts known_conditions and allergies
            profile = (
                db.query(PatientProfile)
                .filter(PatientProfile.user_id == user_id)
                .first()
            )

            if not profile:
                return None

            def _parse_list(val: Any) -> list:
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    # Guard: if value still looks like ciphertext, return empty
                    if val.startswith("gAAAAAB"):
                        logger.warning(
                            "health_summary: field still looks encrypted for user %s — "
                            "check FIELD_ENCRYPTION_KEY env var",
                            user_id,
                        )
                        return []
                    try:
                        return json.loads(val)
                    except Exception:
                        return [val] if val.strip() else []
                return []

            conditions = _parse_list(profile.known_conditions)
            allergies = _parse_list(profile.allergies)

            # Only return block if there's actual data
            if not conditions and not allergies:
                return None

            return {
                "primary_conditions": conditions,
                "secondary_conditions": [],
                "allergies": allergies,
                "blood_type": None,
                "chronic_conditions": [],
            }
        except Exception as exc:
            logger.warning("Error building health_summary for %s: %s", user_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_care_plan(self, db: Session, user_id: str) -> dict | None:
        """Build care plan block. Consumes DB execute #3 (plan) + #4 (tasks).

        Always makes BOTH queries to maintain stable DB call order.
        """
        try:
            # care_plans.patient_id references patient_profiles.id (NOT user.id),
            # and profile.id != user.id — resolve via subselect (same fix as P0).
            # status is stored uppercase by CarePlanStatus (e.g. "ACTIVE"); match
            # case-insensitively so an active plan is actually found.
            plan = db.execute(
                text("""
                    SELECT id, title FROM care_plans
                    WHERE patient_id = (
                            SELECT id FROM patient_profiles WHERE user_id = :uid
                          )
                      AND UPPER(status) = 'ACTIVE'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"uid": user_id},
            ).fetchone()

            if not plan:
                return None

            # care_tasks table may not exist in all environments — skip gracefully
            today_start = dt.datetime.now(dt.UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            plan_id = plan[0]
            try:
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
            except Exception:
                tasks = []

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
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_medications(self, db: Session, user_id: str) -> list | None:
        """Build medications block. Consumes DB execute #5."""
        try:
            rows = db.execute(
                text("""
                    SELECT name, dose, frequency, note, created_at, lifecycle_status
                    FROM medications
                    WHERE patient_id = (
                            SELECT id FROM patient_profiles WHERE user_id = :uid
                          )
                      AND deleted_at IS NULL
                      AND lifecycle_status IN ('active', 'paused')
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
                    # ADR-11: paused stays clinically relevant but must never
                    # read as "currently taking".
                    "status": "đang tạm ngưng" if r[5] == "paused" else "đang dùng",
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Error building medications for %s: %s", user_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
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
                           lr.reference_range, lr.status, lub.test_date,
                           lr.original_test_name, lr.original_value,
                           lr.original_unit, lr.original_reference_range
                    FROM lab_results lr
                    JOIN lab_upload_batches lub ON lub.id = lr.batch_id
                    WHERE lub.patient_id = (
                            SELECT id FROM patient_profiles WHERE user_id = :uid
                          )
                      AND lr.deleted_at IS NULL
                      AND lub.deleted_at IS NULL
                      -- AI2 fix (§J): Meto may only see CONFIRMED lab data. Unverified
                      -- OCR rows persist in lab_results with verified_by_user=False and
                      -- must never enter the AI context. "Confirmed" matches the platform
                      -- definition used everywhere else (lab_provenance / longitudinal /
                      -- insight / narrative): patient- OR doctor-verified. Bound param
                      -- stays dialect-safe.
                      AND (lr.verified_by_user = :verified
                           OR lr.verified_by_doctor = :verified)
                      AND (lub.test_date IS NULL OR lub.test_date >= :cutoff_date)
                    ORDER BY lub.test_date DESC, lr.created_at DESC
                    LIMIT :limit
                """),
                {
                    "uid": user_id,
                    "cutoff_date": cutoff_date,
                    "limit": _MAX_LABS,
                    "verified": True,
                },
            ).fetchall()

            if not rows:
                return None

            def _lab_row(r: Any) -> dict:
                # P0 clinical-integrity: surface the ORIGINAL value+unit as printed
                # (e.g. 88 µmol/L) — NEVER the canonical/SI-converted number. Fall
                # back to the canonical columns only when original_* is NULL.
                orig_test_name = r[6] or r[0]
                orig_value = r[7] if r[7] is not None else r[1]
                orig_unit = r[8] if r[8] is not None else (r[2] or "")
                orig_ref = r[9] if r[9] is not None else (r[3] or "")
                return {
                    "test_name": orig_test_name,
                    # Formatted original — no raw IEEE float, no unit conversion.
                    "value": format_lab_value(orig_value, orig_unit),
                    "unit": orig_unit,
                    # Verbatim token the LLM must quote as-is (never convert/round).
                    "display": format_lab_display(orig_value, orig_unit),
                    "reference_range": orig_ref,
                    "status": r[4] or "unknown",
                    "collected_date": str(r[5])[:10] if r[5] else None,
                }

            return [_lab_row(r) for r in rows]
        except Exception as exc:
            logger.warning("Error building recent_labs for %s: %s", user_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_recent_metrics(self, db: Session, user_id: str) -> list | None:
        """Build recent_metrics block. Consumes DB execute #7."""
        try:
            cutoff = (
                dt.datetime.now(dt.UTC) - dt.timedelta(days=_METRICS_LOOKBACK_DAYS)
            ).isoformat()

            rows = db.execute(
                text("""
                    SELECT metric_type, value, unit, measured_at, status,
                           original_value, original_unit
                    FROM health_metrics
                    WHERE patient_id = (
                            SELECT id FROM patient_profiles WHERE user_id = :uid
                          )
                      AND measured_at >= :cutoff
                      AND deleted_at IS NULL
                      -- AI2 defense-in-depth: only confirmed-source metrics reach
                      -- the AI. NULL = legacy patient data (trusted).
                      AND (source IS NULL OR source IN :sources)
                    ORDER BY measured_at DESC
                    LIMIT 50
                """).bindparams(bindparam("sources", expanding=True)),
                {
                    "uid": user_id,
                    "cutoff": cutoff,
                    "sources": list(_TRUSTED_METRIC_SOURCES),
                },
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
                # P0 clinical-integrity: surface the ORIGINAL value+unit — never the
                # canonical/SI-converted number. Fall back to value/unit when NULL.
                orig_value = r[5] if r[5] is not None else r[1]
                orig_unit = r[6] if r[6] is not None else (r[2] or "")
                result.append({
                    "metric_type": metric_type,
                    "latest_value": format_lab_value(orig_value, orig_unit),
                    "unit": orig_unit,
                    # Verbatim token the LLM must quote as-is (never convert/round).
                    "display": format_lab_display(orig_value, orig_unit),
                    "measured_at": str(r[3]) if r[3] else None,
                    "status": r[4] or "unknown",
                })
                if len(result) >= _MAX_METRICS_TYPES:
                    break

            return result if result else None
        except Exception as exc:
            logger.warning("Error building recent_metrics for %s: %s", user_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
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
        # Midnight-today boundary as an ISO string — portable comparison against
        # the DateTime column across SQLite (tests) and Postgres (prod), avoiding
        # DB-specific date() semantics.
        today_start = dt.datetime.combine(dt.date.today(), dt.time.min).isoformat()
        appointment_list = []

        try:
            # appointments.patient_id references patient_profiles.id (NOT user.id),
            # and profile.id != user.id — resolve via subselect (same fix as P0).
            # Columns match the real appointments schema (scheduled_at/mode/status);
            # the previous title/appointment_time/provider_name/location columns do
            # not exist, so this query always failed and appointments never loaded.
            appts = db.execute(
                text("""
                    SELECT scheduled_at, mode, status, doctor_id
                    FROM appointments
                    WHERE patient_id = (
                            SELECT id FROM patient_profiles WHERE user_id = :uid
                          )
                      AND scheduled_at >= :today_start
                      AND status != 'cancelled'
                    ORDER BY scheduled_at ASC
                    LIMIT 3
                """),
                {"uid": user_id, "today_start": today_start},
            ).fetchall()

            appointment_list = [
                {
                    "title": "Lịch hẹn",
                    "datetime": str(a[0]) if a[0] else None,
                    "mode": a[1] or "",
                    "status": a[2] or "",
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
