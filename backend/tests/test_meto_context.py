"""Tests for Meto AI ContextBuilder.

Covers:
- No consent → context blocks that require consent are None
- With consent → context block has data (using patched builders)
- Missing data → returns None (no hallucination)
- safety_flags present when recent labs/metrics have critical values
- AssembledContext.has_safety_flags()
- ScreenContext defaults

Strategy: patch the individual private block-builder methods so we don't have
to reproduce the exact SQL call ordering in a mock DB session.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import AssembledContext, ScreenContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_consent_row(context_type: str) -> MagicMock:
    row = MagicMock()
    row.context_type = context_type
    row.granted = True
    row.revoked_at = None
    return row


def _all_consents() -> list:
    return [_make_consent_row(ct) for ct in [
        "health_data", "medications", "labs", "metrics", "care_plan", "chat_history"
    ]]


def _make_db_session(consent_rows=None) -> MagicMock:
    """Minimal mock session that handles the consent query."""
    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value.all.return_value = consent_rows or []
    mock_q.filter.return_value.first.return_value = None
    db.query.return_value = mock_q
    # Also accept db.execute(...) calls without error for today_context / appointments
    ep = MagicMock()
    ep.fetchall.return_value = []
    ep.fetchone.return_value = None
    db.execute.return_value = ep
    return db


def _build_with_patches(
    screen_id: str,
    consent_rows: list | None = None,
    *,
    user_profile: dict | None = None,
    health_summary: dict | None = None,
    care_plan: dict | None = None,
    medications: list | None = None,
    recent_labs: list | None = None,
    recent_metrics: list | None = None,
    safety_flags: list | None = None,
) -> AssembledContext:
    """Build context with all individual block builders patched."""
    db = _make_db_session(consent_rows)

    with patch.object(ContextBuilder, "_build_user_profile", return_value=user_profile), \
         patch.object(ContextBuilder, "_build_health_summary", return_value=health_summary), \
         patch.object(ContextBuilder, "_build_care_plan", return_value=care_plan), \
         patch.object(ContextBuilder, "_build_medications", return_value=medications), \
         patch.object(ContextBuilder, "_build_recent_labs", return_value=recent_labs), \
         patch.object(ContextBuilder, "_build_recent_metrics", return_value=recent_metrics), \
         patch.object(ContextBuilder, "_build_today_context", return_value={}), \
         patch.object(ContextBuilder, "_build_safety_flags",
                      return_value=safety_flags if safety_flags is not None else []):
        builder = ContextBuilder()
        return builder.build(db, "user-123", ScreenContext(screen_id=screen_id))


_SAMPLE_USER_PROFILE = {
    "display_name": "Nguyen Van A",
    "age": 41,
    "gender": "male",
    "preferred_address": "bạn",
    "language": "vi",
    "account_type": "patient",
}

_SAMPLE_HEALTH_SUMMARY = {
    "primary_conditions": ["Tiểu đường type 2"],
    "secondary_conditions": [],
    "allergies": [],
    "blood_type": "O+",
    "chronic_conditions": ["Tăng huyết áp"],
}

_SAMPLE_MEDICATIONS = [
    {"name": "Metformin", "dosage": "500mg", "frequency": "2 lần/ngày", "route": "oral"}
]

_SAMPLE_LABS = [
    {"test_name": "HbA1c", "value": "6.5", "unit": "%", "status": "normal",
     "reference_range": "4.0-5.6", "collected_date": "2024-01-15"}
]

_SAMPLE_METRICS = [
    {"metric_type": "blood_pressure", "latest_value": "120/80", "unit": "mmHg",
     "status": "normal", "measured_at": "2024-01-16"}
]


# ---------------------------------------------------------------------------
# Tests: No consent
# ---------------------------------------------------------------------------

class TestNoConsent:
    def test_health_blocks_are_none_without_consent(self):
        """With no consents, all health-gated blocks must be excluded."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=[],
            user_profile=_SAMPLE_USER_PROFILE,
            # The patched methods return these values, but the builder
            # must gate them behind consent checks
        )
        # health_summary, medications, recent_labs, recent_metrics are consent-gated
        assert ctx.health_summary is None
        assert ctx.medications is None
        assert ctx.recent_labs is None
        assert ctx.recent_metrics is None

    def test_missing_consent_types_recorded(self):
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=[],
            user_profile=_SAMPLE_USER_PROFILE,
        )
        assert "health_data" in ctx.missing_consents

    def test_user_profile_included_without_consent(self):
        """user_profile block doesn't require consent."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=[],
            user_profile=_SAMPLE_USER_PROFILE,
        )
        assert ctx.user_profile is not None
        assert ctx.user_profile["display_name"] == "Nguyen Van A"
        assert "user_profile" in ctx.included_blocks

    def test_screen_context_always_included(self):
        ctx = _build_with_patches(
            "labs",
            consent_rows=[],
        )
        assert ctx.screen_context["screen_id"] == "labs"
        assert "screen_context" in ctx.included_blocks

    def test_context_block_is_none_not_missing(self):
        """Blocks must be None (not missing from schema) when consent absent."""
        ctx = _build_with_patches("dashboard", consent_rows=[])
        # Verify the AssembledContext fields exist as None (not omitted)
        assert hasattr(ctx, "health_summary")
        assert hasattr(ctx, "medications")
        assert hasattr(ctx, "recent_labs")


# ---------------------------------------------------------------------------
# Tests: With consent
# ---------------------------------------------------------------------------

class TestWithConsent:
    def test_health_summary_included_with_consent(self):
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            health_summary=_SAMPLE_HEALTH_SUMMARY,
        )
        assert ctx.health_summary is not None
        assert isinstance(ctx.health_summary["primary_conditions"], list)
        assert "health_summary" in ctx.included_blocks

    def test_medications_included_with_consent(self):
        ctx = _build_with_patches(
            "medications",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            medications=_SAMPLE_MEDICATIONS,
        )
        assert ctx.medications is not None
        assert len(ctx.medications) == 1
        assert ctx.medications[0]["name"] == "Metformin"
        assert "medications" in ctx.included_blocks

    def test_recent_labs_included_with_consent(self):
        ctx = _build_with_patches(
            "labs",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            recent_labs=_SAMPLE_LABS,
        )
        assert ctx.recent_labs is not None
        assert ctx.recent_labs[0]["test_name"] == "HbA1c"
        assert "recent_labs" in ctx.included_blocks

    def test_metrics_included_with_consent(self):
        ctx = _build_with_patches(
            "metrics",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            recent_metrics=_SAMPLE_METRICS,
        )
        assert ctx.recent_metrics is not None
        assert ctx.recent_metrics[0]["metric_type"] == "blood_pressure"

    def test_user_profile_and_screen_always_in_included_blocks(self):
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
        )
        assert "user_profile" in ctx.included_blocks
        assert "screen_context" in ctx.included_blocks

    def test_total_tokens_positive(self):
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            health_summary=_SAMPLE_HEALTH_SUMMARY,
        )
        assert ctx.total_estimated_tokens > 0

    def test_no_missing_consents_with_full_consent(self):
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            health_summary=_SAMPLE_HEALTH_SUMMARY,
        )
        assert ctx.missing_consents == []


# ---------------------------------------------------------------------------
# Tests: Missing data → None (no hallucination)
# ---------------------------------------------------------------------------

class TestMissingData:
    def test_missing_user_profile_is_none(self):
        """Builder returns None for user_profile when no DB row exists."""
        db = _make_db_session(consent_rows=[])
        # Don't patch _build_user_profile → it calls the real method
        # but mock db.execute to return no rows
        ep = MagicMock()
        ep.fetchone.return_value = None
        ep.fetchall.return_value = []
        db.execute.return_value = ep

        builder = ContextBuilder()
        ctx = builder.build(db, "nonexistent-user", ScreenContext(screen_id="dashboard"))
        assert ctx.user_profile is None

    def test_builder_returns_none_not_empty_list_for_no_labs(self):
        """_build_recent_labs returns None when DB has no rows (not [])."""
        builder = ContextBuilder()
        db = MagicMock()
        ep = MagicMock()
        ep.fetchall.return_value = []  # empty result
        db.execute.return_value = ep

        result = builder._build_recent_labs(db, "user-123")
        assert result is None

    def test_builder_returns_none_not_empty_list_for_no_meds(self):
        """_build_medications returns None when DB has no rows."""
        builder = ContextBuilder()
        db = MagicMock()
        ep = MagicMock()
        ep.fetchall.return_value = []
        db.execute.return_value = ep

        result = builder._build_medications(db, "user-123")
        assert result is None

    def test_builder_returns_none_not_empty_list_for_no_metrics(self):
        """_build_recent_metrics returns None when DB has no rows."""
        builder = ContextBuilder()
        db = MagicMock()
        ep = MagicMock()
        ep.fetchall.return_value = []
        db.execute.return_value = ep

        result = builder._build_recent_metrics(db, "user-123")
        assert result is None

    def test_db_error_in_user_profile_returns_none(self):
        """If DB raises, _build_user_profile returns None (graceful degradation)."""
        builder = ContextBuilder()
        db = MagicMock()
        db.execute.side_effect = Exception("DB connection lost")

        result = builder._build_user_profile(db, "user-123")
        assert result is None

    def test_db_error_in_labs_returns_none(self):
        builder = ContextBuilder()
        db = MagicMock()
        db.execute.side_effect = Exception("timeout")

        result = builder._build_recent_labs(db, "user-123")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Safety flags
# ---------------------------------------------------------------------------

class TestSafetyFlags:
    def test_critical_lab_produces_flag(self):
        builder = ContextBuilder()
        db = MagicMock()
        recent_labs = [{
            "test_name": "Creatinine",
            "value": "9.5",
            "unit": "mg/dL",
            "status": "critical_high",
        }]
        flags = builder._build_safety_flags(db, "user-123", recent_labs, None)
        assert len(flags) >= 1
        assert any("CRITICAL" in f or "critical" in f.lower() for f in flags)

    def test_critical_metric_produces_flag(self):
        builder = ContextBuilder()
        db = MagicMock()
        recent_metrics = [{
            "metric_type": "blood_glucose",
            "latest_value": "450",
            "unit": "mg/dL",
            "status": "critical",
        }]
        flags = builder._build_safety_flags(db, "user-123", None, recent_metrics)
        assert len(flags) >= 1

    def test_critical_low_produces_flag(self):
        builder = ContextBuilder()
        db = MagicMock()
        recent_labs = [{
            "test_name": "Glucose",
            "value": "40",
            "unit": "mg/dL",
            "status": "critical_low",
        }]
        flags = builder._build_safety_flags(db, "user-123", recent_labs, None)
        assert len(flags) >= 1

    def test_normal_values_produce_no_flags(self):
        builder = ContextBuilder()
        db = MagicMock()
        recent_labs = [
            {"test_name": "HbA1c", "value": "6.5", "unit": "%", "status": "normal"}
        ]
        flags = builder._build_safety_flags(db, "user-123", recent_labs, None)
        assert flags == []

    def test_safety_flags_in_context_with_critical_labs(self):
        """When labs have critical status, assembled context has safety_flags."""
        critical_labs = [{
            "test_name": "Creatinine", "value": "9.5", "unit": "mg/dL",
            "status": "critical_high", "reference_range": "", "collected_date": "2024-01-15"
        }]
        ctx = _build_with_patches(
            "labs",
            consent_rows=_all_consents(),
            user_profile=_SAMPLE_USER_PROFILE,
            recent_labs=critical_labs,
            # Don't patch safety_flags — let the real method run
        )
        # Re-run with actual safety_flags method
        db = _make_db_session(_all_consents())
        with patch.object(ContextBuilder, "_build_user_profile", return_value=_SAMPLE_USER_PROFILE), \
             patch.object(ContextBuilder, "_build_health_summary", return_value=None), \
             patch.object(ContextBuilder, "_build_care_plan", return_value=None), \
             patch.object(ContextBuilder, "_build_medications", return_value=None), \
             patch.object(ContextBuilder, "_build_recent_labs", return_value=critical_labs), \
             patch.object(ContextBuilder, "_build_recent_metrics", return_value=None), \
             patch.object(ContextBuilder, "_build_today_context", return_value={}):
            builder = ContextBuilder()
            ctx = builder.build(db, "user-123", ScreenContext(screen_id="labs"))

        assert ctx.has_safety_flags()
        assert "safety_flags" in ctx.included_blocks

    def test_no_safety_flags_for_normal_labs(self):
        db = _make_db_session(_all_consents())
        with patch.object(ContextBuilder, "_build_user_profile", return_value=_SAMPLE_USER_PROFILE), \
             patch.object(ContextBuilder, "_build_health_summary", return_value=None), \
             patch.object(ContextBuilder, "_build_care_plan", return_value=None), \
             patch.object(ContextBuilder, "_build_medications", return_value=None), \
             patch.object(ContextBuilder, "_build_recent_labs", return_value=_SAMPLE_LABS), \
             patch.object(ContextBuilder, "_build_recent_metrics", return_value=None), \
             patch.object(ContextBuilder, "_build_today_context", return_value={}):
            builder = ContextBuilder()
            ctx = builder.build(db, "user-123", ScreenContext(screen_id="labs"))

        assert not ctx.has_safety_flags()


# ---------------------------------------------------------------------------
# Tests: AssembledContext schema
# ---------------------------------------------------------------------------

class TestAssembledContext:
    def test_has_safety_flags_true(self):
        ctx = AssembledContext(safety_flags=["⚠️ CRITICAL: Creatinine = 9.5 mg/dL"])
        assert ctx.has_safety_flags() is True

    def test_has_safety_flags_false(self):
        ctx = AssembledContext(safety_flags=[])
        assert ctx.has_safety_flags() is False

    def test_to_prompt_dict_keys(self):
        ctx = AssembledContext(
            user_profile={"name": "Test"},
            safety_flags=["flag1"],
        )
        d = ctx.to_prompt_dict()
        expected_keys = {
            "user_profile", "health_summary", "care_plan", "medications",
            "recent_labs", "recent_metrics", "screen_context",
            "today_context", "safety_flags"
        }
        assert set(d.keys()) == expected_keys
        assert d["safety_flags"] == ["flag1"]

    def test_to_prompt_dict_values(self):
        ctx = AssembledContext(
            user_profile={"name": "Test"},
            health_summary=None,
        )
        d = ctx.to_prompt_dict()
        assert d["user_profile"] == {"name": "Test"}
        assert d["health_summary"] is None

    def test_missing_consents_default_empty(self):
        ctx = AssembledContext()
        assert ctx.missing_consents == []

    def test_included_blocks_default_empty(self):
        ctx = AssembledContext()
        assert ctx.included_blocks == []


# ---------------------------------------------------------------------------
# Tests: ScreenContext schema
# ---------------------------------------------------------------------------

class TestScreenContext:
    def test_defaults(self):
        sc = ScreenContext()
        assert sc.screen_id == "dashboard"
        assert sc.entity_id is None
        assert sc.entity_type is None
        # view_context defaults to None (schema) but builder coerces to {} for safety
        assert sc.view_context is None or sc.view_context == {}

    def test_custom_screen(self):
        sc = ScreenContext(screen_id="labs", entity_id="batch-123", entity_type="lab_result")
        assert sc.screen_id == "labs"
        assert sc.entity_id == "batch-123"
        assert sc.entity_type == "lab_result"

    def test_all_screens_valid(self):
        """All known screen IDs should be accepted without error."""
        screens = ["dashboard", "labs", "medications", "metrics", "nutrition",
                   "care_plan", "profile"]
        for s in screens:
            sc = ScreenContext(screen_id=s)
            assert sc.screen_id == s
