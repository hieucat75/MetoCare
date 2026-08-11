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

from app.ai.consent_policy import (
    BLOCK_CONSENT_CATEGORY,
    CATEGORY_DOCTOR_CONSULTATION,
    CATEGORY_HEALTH_RECORDS,
    CATEGORY_MEDICATIONS,
    load_granted_categories,
)
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.models.patient import PatientProfile
from app.models.user import User
from app.utils.number_format import format_lab_display, format_lab_value

logger = logging.getLogger(__name__)


def _record_degraded(sink: list[str] | None, block: str) -> None:
    """Note that `block`'s query RAISED, if the caller is collecting failures.

    The sink is optional so a builder can still be called in isolation, but
    `build()` always passes one — that is the path whose output reaches the model.
    """
    if sink is not None and block not in sink:
        sink.append(block)

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

# Per-block consent categories now live in app/ai/consent_policy.BLOCK_CONSENT_CATEGORY.

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

# ---------------------------------------------------------------------------
# AI-F1 — free-text sanitisation before anything enters the system prompt.
#
# OCR'd document text reaches the context through the MDI promoters (medication
# name / note, condition and allergy lists, care-plan and lab labels). That text
# is attacker-controllable: whoever prints the document the patient photographs
# writes it. Assembled context is embedded in the SYSTEM message, i.e. the
# highest-trust position of the prompt, so any instruction it carries would be
# read as an instruction. Defence in depth (layer 1 of 3; the other two are the
# fenced block + the untrusted-data rule in prompt/assembler.py):
#   - drop any field the platform's own injection detector flags, and
#   - hard-cap every free-text field so a long payload cannot flood the prompt.
# ---------------------------------------------------------------------------

_MAX_FREE_TEXT_CHARS = 200
_FILTERED_PLACEHOLDER = "[nội dung đã được lọc vì lý do an toàn]"


def _sanitize_text(value: Any) -> str:
    """Return `value` as prompt-safe text: injection-filtered and length-capped."""
    if value is None:
        return ""
    text = str(value)
    if not text.strip():
        return ""

    from app.domain.guardrails import is_injection

    try:
        flagged = is_injection(text)
    except Exception as exc:  # pragma: no cover - detector must never break build
        logger.warning("Injection detector failed; dropping field: %s", exc)
        flagged = True
    if flagged:
        logger.warning("AI context: injection-flagged free text dropped from prompt")
        return _FILTERED_PLACEHOLDER

    if len(text) > _MAX_FREE_TEXT_CHARS:
        return text[:_MAX_FREE_TEXT_CHARS] + "…"
    return text


def _sanitize_unit(unit: Any) -> str:
    """Sanitize a measurement unit. A flagged/oversized unit becomes empty rather
    than the placeholder text, so `display` stays a clean "<value>" token."""
    safe = _sanitize_text(unit)
    return "" if safe == _FILTERED_PLACEHOLDER else safe


def _sanitize_list(values: Any) -> list[str]:
    """Sanitize every entry of a free-text list, dropping empties."""
    if not isinstance(values, list):
        return []
    return [s for s in (_sanitize_text(v) for v in values) if s]



def _ctx_guarded_status(row, status_index: int, canonical_index: int = 0):
    """Stored status, unless the analyte/unit pair is not interpretable.

    `reclassify` only walks lab_results and is operator-run, so between deploy
    and its next pass a legacy CBC row still carries `critical`. Everything in
    this module is fed verbatim to the model.
    """
    from app.domain.analyte_units import guarded_status

    try:
        canonical, value, unit = row[canonical_index], row[1], row[2]
        g = guarded_status(canonical, value, unit)
        if g is not None and g[0] == "unknown":
            return "unknown"
    except Exception:  # noqa: BLE001 — context building must never raise
        pass
    return row[status_index]


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

        # Per-category consent gate (BRD §J) — fail-closed AND data-minimizing:
        # PHI for a category is neither queried nor included unless that category
        # is actively granted at the current policy version. Categories the screen
        # would use but that are not granted are surfaced in missing_consents so
        # the client can prompt for consent. The master ai_processing gate is
        # enforced upstream in the chat service (no build without it).
        granted_categories = load_granted_categories(db, user_id)
        health_ok = CATEGORY_HEALTH_RECORDS in granted_categories
        meds_ok = CATEGORY_MEDICATIONS in granted_categories
        consult_ok = CATEGORY_DOCTOR_CONSULTATION in granted_categories

        included_blocks: list[str] = []
        # Blocks whose query RAISED. Distinct from a block that is absent because
        # the patient consented but has no rows — see AssembledContext.
        degraded: list[str] = []
        missing_consents = list(
            dict.fromkeys(
                category
                for block, category in BLOCK_CONSENT_CATEGORY.items()
                if block in screen_blocks and category not in granted_categories
            )
        )
        total_tokens = 0

        # ---------------------------------------------------------------
        # Fixed DB call order: queries happen regardless of consent/screen
        # Results are gated afterwards.
        # ---------------------------------------------------------------

        # Each _build_* method has its own try/except and returns None on failure.
        # The context builder now receives a dedicated session (ctx_db) that is
        # separate from the main request session, so SQL errors here cannot
        # poison the conversation/message writes in the main session.

        # DB call #1: user profile (non-clinical identity — always allowed)
        raw_user_profile = self._build_user_profile(db, user_id, degraded)

        # Clinical blocks are queried ONLY when their category is consented, so
        # non-consented PHI is never even loaded into memory (data-minimization).
        # DB call #2: health summary
        raw_health_summary = self._build_health_summary(db, user_id, degraded) if health_ok else None

        # DB calls #3+#4: care plan + tasks (always called together)
        raw_care_plan = self._build_care_plan(db, user_id, degraded) if health_ok else None

        # DB call #5: medications
        raw_medications = self._build_medications(db, user_id, degraded) if meds_ok else None

        # DB call #6: recent labs
        raw_recent_labs = self._build_recent_labs(db, user_id, degraded) if health_ok else None

        # DB call #7: recent metrics
        raw_recent_metrics = self._build_recent_metrics(db, user_id, degraded) if health_ok else None

        # DB call #8: appointments (for today_context)
        raw_today_context = self._build_today_context(db, user_id, degraded) if consult_ok else None

        # ---------------------------------------------------------------
        # Assemble: a block is included when its category was consented (the raw
        # value is None otherwise, per the gated queries above), the screen uses
        # it, and it has data.
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

        # safety_flags — derived from labs/metrics, so gated on health_records
        # consent. Without it there are no labs/metrics to derive from anyway.
        safety_flags = (
            self._build_safety_flags(db, user_id, recent_labs, recent_metrics)
            if health_ok
            else []
        )
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
            degraded_blocks=degraded,
        )

    # -----------------------------------------------------------------------
    # Block builders — each consumes exactly ONE db.execute() call
    # (except care_plan which consumes TWO: plan + tasks)
    # -----------------------------------------------------------------------

    def _build_user_profile(self, db: Session, user_id: str, degraded: list[str] | None = None) -> dict | None:
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
                # AI-F1: user-supplied free text, sanitized like every other
                # free-text field that lands in the system prompt.
                "display_name": _sanitize_text(display_name) or "Người dùng",
                "age": age,
                "gender": (profile.gender if profile else None) or "unknown",
                "preferred_address": "bạn",
                "language": "vi",
                "account_type": "patient",
            }
        except Exception as exc:
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building user_profile for %s: %s", user_id, exc)
            _record_degraded(degraded, "user_profile")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_health_summary(self, db: Session, user_id: str, degraded: list[str] | None = None) -> dict | None:
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

            # AI-F1: conditions/allergies can be promoted from OCR'd documents.
            conditions = _sanitize_list(_parse_list(profile.known_conditions))
            allergies = _sanitize_list(_parse_list(profile.allergies))

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
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building health_summary for %s: %s", user_id, exc)
            _record_degraded(degraded, "health_summary")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_care_plan(self, db: Session, user_id: str, degraded: list[str] | None = None) -> dict | None:
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
                    # AI-F1: free-text task titles are sanitized like every other
                    # free-text field that reaches the system prompt.
                    "title": _sanitize_text(t[0]),
                    "due_date": str(t[1]) if t[1] else None,
                    "status": t[2] or "pending",
                    "priority": t[3] or "medium",
                })

            completed = sum(1 for t in task_list if t["status"] == "completed")
            return {
                "plan_name": _sanitize_text(plan[1]),
                "active_tasks": task_list[:10],
                "completed_today": completed,
                "total_today": len(task_list),
            }
        except Exception as exc:
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building care_plan for %s: %s", user_id, exc)
            _record_degraded(degraded, "care_plan")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_medications(self, db: Session, user_id: str, degraded: list[str] | None = None) -> list | None:
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

            # AI-F1: name/dose/frequency/note all originate from OCR promotion for
            # documents-sourced rows — sanitize every one before it can reach the
            # system prompt.
            return [
                {
                    "name": _sanitize_text(r[0]),
                    "dosage": _sanitize_text(r[1]),
                    "frequency": _sanitize_text(r[2]),
                    "note": _sanitize_text(r[3]),
                    "start_date": str(r[4])[:10] if r[4] else None,
                    # ADR-11: paused stays clinically relevant but must never
                    # read as "currently taking".
                    "status": "đang tạm ngưng" if r[5] == "paused" else "đang dùng",
                }
                for r in rows
            ]
        except Exception as exc:
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building medications for %s: %s", user_id, exc)
            _record_degraded(degraded, "medications")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_recent_labs(self, db: Session, user_id: str, degraded: list[str] | None = None) -> list | None:
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
                           lr.original_unit, lr.original_reference_range,
                           lr.canonical_name
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
                # AI-F1: OCR-derived labels are sanitized. The unit is sanitized
                # BEFORE `display` is formatted so the verbatim-quote token stays
                # consistent with the unit field (real units are never altered).
                orig_unit = _sanitize_unit(orig_unit)
                return {
                    "test_name": _sanitize_text(orig_test_name),
                    # Formatted original — no raw IEEE float, no unit conversion.
                    "value": format_lab_value(orig_value, orig_unit),
                    "unit": orig_unit,
                    # Verbatim token the LLM must quote as-is (never convert/round).
                    "display": format_lab_display(orig_value, orig_unit),
                    "reference_range": _sanitize_text(orig_ref),
                    "status": _ctx_guarded_status(r, 4, canonical_index=10) or "unknown",
                    "collected_date": str(r[5])[:10] if r[5] else None,
                }

            return [_lab_row(r) for r in rows]
        except Exception as exc:
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building recent_labs for %s: %s", user_id, exc)
            _record_degraded(degraded, "recent_labs")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def _build_recent_metrics(self, db: Session, user_id: str, degraded: list[str] | None = None) -> list | None:
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
                orig_unit = _sanitize_unit(r[6] if r[6] is not None else (r[2] or ""))
                result.append({
                    "metric_type": _sanitize_text(metric_type),
                    "latest_value": format_lab_value(orig_value, orig_unit),
                    "unit": orig_unit,
                    # Verbatim token the LLM must quote as-is (never convert/round).
                    "display": format_lab_display(orig_value, orig_unit),
                    "measured_at": str(r[3]) if r[3] else None,
                    "status": _ctx_guarded_status(r, 4) or "unknown",
                })
                if len(result) >= _MAX_METRICS_TYPES:
                    break

            return result if result else None
        except Exception as exc:
            # Record the FAILURE distinctly from an empty result — see
            # AssembledContext.degraded_blocks. Returning None alone made a failed
            # query indistinguishable from "the patient has no data", which for a
            # clinical block reads to the model as reassurance.
            logger.warning("Error building recent_metrics for %s: %s", user_id, exc)
            _record_degraded(degraded, "recent_metrics")
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

    def _build_today_context(self, db: Session, user_id: str, degraded: list[str] | None = None) -> dict:
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
            # Same class as the six builders above: returning an empty
            # appointment list makes a failed query indistinguishable from "no
            # appointments today". It was `logger.debug`, so it was silent in
            # logs as well. today_context is not in SAFETY_CRITICAL_BLOCKS — a
            # missing appointment is not a false reassurance about a lab value —
            # but the model should still not assert the patient has nothing
            # scheduled when we simply could not look.
            logger.warning("today_context appointment query failed: %s", exc)
            _record_degraded(degraded, "today_context")

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
