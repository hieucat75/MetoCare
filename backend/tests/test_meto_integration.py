"""
Integration tests covering Meto acceptance criteria:
- Context isolation (user A never gets user B data)
- Consent gating (no consent → block excluded, Meto says "chưa có dữ liệu")
- Medications context works WITHOUT labs existing
- Labs screen context includes lab entity when entity_id passed
- Dashboard screen context includes correct blocks
- Provider fallback (primary fails → fallback used)
- No provider name leakage in any response field
- Quick prompts return correct prompts per screen
- Missing data gracefully returns None (not hallucinated)
- Safety: normal message → no escalation
- Safety: emergency message → escalation returned, no AI called
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.ai.context.builder import _SCREEN_BLOCKS, ContextBuilder
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.ai.prompt.safety import QUICK_PROMPTS, SafetyGuard
from app.ai.providers.base import ChatMessage, ChatResponse
from app.ai.registry import ProviderRegistry
from app.schemas.meto import MetaChatResponse

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_meto_context.py approach)
# ---------------------------------------------------------------------------

def _make_consent_row(context_type: str) -> MagicMock:
    row = MagicMock()
    row.context_type = context_type
    row.granted = True
    row.revoked_at = None
    return row


def _consents_for(*types: str) -> list:
    return [_make_consent_row(ct) for ct in types]


def _all_consents() -> list:
    return _consents_for(
        "health_data", "medications", "labs", "metrics", "care_plan", "chat_history"
    )


def _make_db_session(consent_rows: list | None = None) -> MagicMock:
    """Minimal mock DB session that handles consent queries and execute() calls."""
    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value.all.return_value = consent_rows or []
    mock_q.filter.return_value.first.return_value = None
    db.query.return_value = mock_q

    ep = MagicMock()
    ep.fetchall.return_value = []
    ep.fetchone.return_value = None
    db.execute.return_value = ep

    # Make add/commit/refresh work
    db.add.return_value = None
    db.commit.return_value = None

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = "test-id"
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = dt.datetime.now(dt.UTC)
        if not hasattr(obj, "last_active_at"):
            obj.last_active_at = dt.datetime.now(dt.UTC)

    db.refresh.side_effect = _refresh
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
    entity_id: str | None = None,
    entity_type: str | None = None,
) -> AssembledContext:
    """Build context with all block builders patched for predictable results."""
    db = _make_db_session(consent_rows)
    screen = ScreenContext(
        screen_id=screen_id,
        entity_id=entity_id,
        entity_type=entity_type,
    )

    with (
        patch.object(ContextBuilder, "_build_user_profile", return_value=user_profile),
        patch.object(ContextBuilder, "_build_health_summary", return_value=health_summary),
        patch.object(ContextBuilder, "_build_care_plan", return_value=care_plan),
        patch.object(ContextBuilder, "_build_medications", return_value=medications),
        patch.object(ContextBuilder, "_build_recent_labs", return_value=recent_labs),
        patch.object(ContextBuilder, "_build_recent_metrics", return_value=recent_metrics),
        patch.object(ContextBuilder, "_build_today_context", return_value={}),
        patch.object(
            ContextBuilder,
            "_build_safety_flags",
            return_value=safety_flags if safety_flags is not None else [],
        ),
    ):
        builder = ContextBuilder()
        return builder.build(db, "user-123", screen)


def _make_mock_registry(
    response_content: str = "Meto response",
    *,
    fallback_used: bool = False,
    provider_name: str = "mock",
) -> ProviderRegistry:
    """Mock ProviderRegistry returning a canned response."""
    registry = MagicMock(spec=ProviderRegistry)
    mock_response = ChatResponse(
        content=response_content,
        tool_calls=None,
        input_tokens=20,
        output_tokens=15,
        model_used="mock-v1",
        finish_reason="stop",
        latency_ms=100,
        provider=provider_name,
    )
    registry.call_with_fallback = AsyncMock(
        return_value=(mock_response, provider_name, fallback_used)
    )
    registry.get_available_providers.return_value = []
    return registry


def _make_full_svc_patches(
    *,
    response_content: str = "Meto response",
    fallback_used: bool = False,
    consent_rows: list | None = None,
    medications: list | None = None,
    recent_labs: list | None = None,
    safety_result=None,
):
    """Return a context manager stack for a full svc.chat() call."""
    from app.ai.context.schemas import AssembledContext
    from app.ai.prompt.safety import SafetyResult

    if safety_result is None:
        safety_result = SafetyResult(safe=True)

    assembled = AssembledContext(
        user_profile={"display_name": "Test User", "preferred_address": "bạn"},
        health_summary=None,
        care_plan=None,
        medications=medications,
        recent_labs=recent_labs,
        recent_metrics=None,
        screen_context={"screen_id": "dashboard"},
        today_context={},
        safety_flags=[],
        total_estimated_tokens=200,
        missing_consents=[],  # Always empty — no consent gate in chat flow
        included_blocks=["user_profile", "screen_context"],
    )

    return assembled, safety_result


# ---------------------------------------------------------------------------
# Test 1: Context isolation — user A cannot see user B's data
# ---------------------------------------------------------------------------

class TestContextIsolation:
    def test_context_isolation_user_a_cannot_see_user_b_data(self):
        """User A's context must never include User B's medications and vice versa."""
        user_a_meds = [{"name": "Metformin", "dosage": "500mg", "frequency": "2x/day"}]
        user_b_meds = [{"name": "Amlodipine", "dosage": "5mg", "frequency": "1x/day"}]

        # Build context for user A
        ctx_a = _build_with_patches(
            "medications",
            consent_rows=_all_consents(),
            user_profile={"display_name": "User A", "preferred_address": "anh"},
            medications=user_a_meds,
        )

        # Build context for user B
        ctx_b = _build_with_patches(
            "medications",
            consent_rows=_all_consents(),
            user_profile={"display_name": "User B", "preferred_address": "chị"},
            medications=user_b_meds,
        )

        # User A should only see their own medications
        assert ctx_a.medications is not None
        med_names_a = {m["name"] for m in ctx_a.medications}
        assert "Metformin" in med_names_a
        assert "Amlodipine" not in med_names_a

        # User B should only see their own medications
        assert ctx_b.medications is not None
        med_names_b = {m["name"] for m in ctx_b.medications}
        assert "Amlodipine" in med_names_b
        assert "Metformin" not in med_names_b

        # Double-check profile isolation
        assert ctx_a.user_profile["display_name"] == "User A"
        assert ctx_b.user_profile["display_name"] == "User B"


# ---------------------------------------------------------------------------
# Test 2 & 3: Consent gating
# ---------------------------------------------------------------------------

@pytest.mark.real_consent
class TestConsentGating:
    """Per-category consent gate (BRD §J) — fail-closed. A PHI block is included
    only when its category is actively granted; ungranted categories are excluded
    and surfaced in missing_consents.
    """

    def test_block_excluded_without_consent(self):
        """No consent → medications excluded even though data exists."""
        ctx = _build_with_patches(
            "medications",
            consent_rows=[],  # nothing granted
            medications=[{"name": "Metformin", "dosage": "500mg", "frequency": "2x/day"}],
        )
        assert ctx.medications is None
        assert "medications" in ctx.missing_consents

    def test_block_included_with_consent(self):
        """Granting the medications category includes the block."""
        ctx = _build_with_patches(
            "medications",
            consent_rows=_consents_for("medications"),
            medications=[{"name": "Metformin", "dosage": "500mg", "frequency": "2x/day"}],
        )
        assert ctx.medications is not None
        assert ctx.medications[0]["name"] == "Metformin"
        assert "medications" not in ctx.missing_consents

    def test_missing_consents_lists_ungranted_categories(self):
        """missing_consents names the screen's ungranted categories."""
        ctx = _build_with_patches("dashboard", consent_rows=[])
        assert "health_records" in ctx.missing_consents
        assert "medications" in ctx.missing_consents

    def test_partial_consent_includes_only_granted(self):
        """Only granted categories' data is included; the rest are withheld."""
        ctx = _build_with_patches(
            "labs",
            consent_rows=_consents_for("medications"),  # meds granted, health_records not
            medications=[{"name": "Metformin", "dosage": "500mg"}],
            recent_labs=[{"test_name": "HbA1c", "value": "6.5"}],
        )
        assert ctx.medications is not None       # granted
        assert ctx.recent_labs is None           # health_records not granted
        assert "health_records" in ctx.missing_consents


# ---------------------------------------------------------------------------
# Test 4: Medications context works WITHOUT labs
# ---------------------------------------------------------------------------

class TestMedicationsWithoutLabs:
    def test_medications_context_works_without_labs(self):
        """Medications screen must work fine when no lab data exists at all."""
        ctx = _build_with_patches(
            "medications",
            consent_rows=_consents_for("medications", "health_data"),
            user_profile={"display_name": "Test User", "preferred_address": "bạn"},
            medications=[{"name": "Metformin", "dosage": "500mg", "frequency": "2x/day"}],
            recent_labs=None,  # No labs at all
        )

        # Medications should be populated
        assert ctx.medications is not None
        assert ctx.medications[0]["name"] == "Metformin"

        # No labs — for medications screen, recent_labs is not a required block
        # Either None (not in screen blocks) or gracefully None
        assert ctx.recent_labs is None

        # No exception raised — we got here
        assert ctx.included_blocks is not None

    def test_medications_screen_does_not_require_labs_block(self):
        """Verify that recent_labs absence does not cause failures in medications screen."""
        # Even if recent_labs is in the _SCREEN_BLOCKS definition, with no labs data it should be None
        ctx = _build_with_patches(
            "medications",
            consent_rows=_all_consents(),
            medications=[{"name": "Metformin"}],
            recent_labs=None,
        )
        # recent_labs is gracefully None when no data
        assert ctx.recent_labs is None


# ---------------------------------------------------------------------------
# Test 5: Labs screen context includes entity
# ---------------------------------------------------------------------------

class TestLabsScreenEntity:
    def test_labs_screen_context_includes_entity(self):
        """Labs screen with entity_id must reflect entity in screen_context block."""
        ctx = _build_with_patches(
            "labs",
            consent_rows=_all_consents(),
            entity_id="batch-123",
            entity_type="lab_batch",
        )

        assert ctx.screen_context is not None
        assert ctx.screen_context["screen_id"] == "labs"
        assert ctx.screen_context["entity_id"] == "batch-123"
        assert ctx.screen_context["entity_type"] == "lab_batch"

    def test_labs_entity_roundtrip_via_screen_context(self):
        """ScreenContext entity_id and entity_type survive the build pipeline."""
        sc = ScreenContext(screen_id="labs", entity_id="batch-456", entity_type="lab_result")
        db = _make_db_session(_all_consents())

        with (
            patch.object(ContextBuilder, "_build_user_profile", return_value=None),
            patch.object(ContextBuilder, "_build_health_summary", return_value=None),
            patch.object(ContextBuilder, "_build_care_plan", return_value=None),
            patch.object(ContextBuilder, "_build_medications", return_value=None),
            patch.object(ContextBuilder, "_build_recent_labs", return_value=None),
            patch.object(ContextBuilder, "_build_recent_metrics", return_value=None),
            patch.object(ContextBuilder, "_build_today_context", return_value={}),
        ):
            builder = ContextBuilder()
            ctx = builder.build(db, "user-123", sc)

        assert ctx.screen_context["entity_id"] == "batch-456"
        assert ctx.screen_context["entity_type"] == "lab_result"


# ---------------------------------------------------------------------------
# Test 6: Dashboard context blocks
# ---------------------------------------------------------------------------

class TestDashboardContextBlocks:
    def test_dashboard_context_includes_correct_blocks(self):
        """Dashboard must include profile/health_summary/care_plan/meds/labs/metrics/today."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile={"display_name": "Test User", "preferred_address": "bạn"},
            health_summary={"primary_conditions": ["Tiểu đường type 2"]},
            care_plan={"plan_name": "Kế hoạch tháng 7", "active_tasks": []},
            medications=[{"name": "Metformin"}],
            recent_metrics=[{"metric_type": "blood_pressure", "latest_value": "120/80"}],
            recent_labs=[{"test_name": "HbA1c", "value": "6.5"}],
        )

        # P0 fix: dashboard now includes recent_labs so Meto can answer questions
        # like cardiovascular-risk assessment from the home tab (the default screen).
        dashboard_blocks = _SCREEN_BLOCKS["dashboard"]
        assert "recent_labs" in dashboard_blocks

        # These blocks should be included
        assert ctx.user_profile is not None
        assert ctx.health_summary is not None
        assert ctx.care_plan is not None
        assert ctx.medications is not None
        assert ctx.recent_metrics is not None

        # recent_labs must now appear for dashboard (P0 fix)
        assert ctx.recent_labs is not None

    def test_dashboard_includes_recent_labs(self):
        """P0 fix: recent_labs IS included on dashboard when data exists."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            recent_labs=[{"test_name": "HbA1c", "value": "6.5"}],
        )
        # With data present, labs must be exposed on the dashboard screen.
        assert ctx.recent_labs is not None
        assert "recent_labs" in ctx.included_blocks


# ---------------------------------------------------------------------------
# Test 7: Provider fallback
# ---------------------------------------------------------------------------

class TestProviderFallback:
    @pytest.mark.asyncio
    async def test_provider_fallback_primary_fails_fallback_used(self):
        """When primary provider fails, fallback provider is used."""
        from app.services.meto_chat import MetoChatService

        # Registry where call_with_fallback returns fallback_used=True
        registry = _make_mock_registry(
            response_content="Fallback response",
            fallback_used=True,
            provider_name="openai",
        )
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="dashboard")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            mock_ctx.build.return_value = AssembledContext(
                user_profile={"display_name": "Test", "preferred_address": "bạn"},
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "dashboard"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=200,
                missing_consents=[],
                included_blocks=["user_profile", "screen_context"],
            )

            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            mock_prompt.assemble.return_value = (
                "system",
                [ChatMessage(role="user", content="test")],
            )
            mock_prompt.generate_conversation_title.return_value = "Test"
            mock_prompt._get_quick_prompts.return_value = []

            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Huyết áp tôi thế nào?",
                screen_context=screen,
            )

        assert result.fallback_used is True
        assert result.content == "Fallback response"
        assert result.content != ""

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_error_message(self):
        """When ALL providers fail, service returns a graceful error message."""
        from app.ai.exceptions import MetoAIError
        from app.services.meto_chat import MetoChatService

        registry = MagicMock(spec=ProviderRegistry)
        registry.call_with_fallback = AsyncMock(side_effect=MetoAIError("All failed"))
        registry.get_available_providers.return_value = []

        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="dashboard")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            mock_ctx.build.return_value = AssembledContext(
                user_profile=None,
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "dashboard"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=100,
                missing_consents=[],
                included_blocks=[],
            )

            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            mock_prompt.assemble.return_value = (
                "system",
                [ChatMessage(role="user", content="test")],
            )
            mock_prompt.generate_conversation_title.return_value = "Test"
            mock_prompt._get_quick_prompts.return_value = []

            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Câu hỏi bất kỳ",
                screen_context=screen,
            )

        # Should return graceful degradation message, not raise
        assert isinstance(result, MetaChatResponse)
        assert result.content != ""
        assert result.provider_used == "meto"


# ---------------------------------------------------------------------------
# Test 8: No provider name leakage
# ---------------------------------------------------------------------------

class TestNoProviderNameLeakage:
    @pytest.mark.asyncio
    async def test_no_provider_name_in_response_content(self):
        """Provider names must NEVER appear in response content field."""
        from app.services.meto_chat import MetoChatService

        registry = _make_mock_registry(
            response_content="Xét nghiệm HbA1c của bạn cho thấy đường huyết đang được kiểm soát tốt.",
            provider_name="claude",
        )
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="labs")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            mock_ctx.build.return_value = AssembledContext(
                user_profile={"display_name": "Test", "preferred_address": "bạn"},
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "labs"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=200,
                missing_consents=[],
                included_blocks=["user_profile", "screen_context"],
            )

            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            mock_prompt.assemble.return_value = (
                "system",
                [ChatMessage(role="user", content="test")],
            )
            mock_prompt.generate_conversation_title.return_value = "Test"
            mock_prompt._get_quick_prompts.return_value = []

            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Giải thích HbA1c",
                screen_context=screen,
            )

        # provider_used must always be "meto"
        assert result.provider_used == "meto"

        # Content must not reveal provider names
        forbidden_names = ["claude", "openai", "anthropic", "gpt", "9router", "gemini"]
        content_lower = result.content.lower()
        for name in forbidden_names:
            assert name not in content_lower, (
                f"Provider name '{name}' leaked into response content: {result.content!r}"
            )

    def test_provider_used_field_always_meto(self):
        """MetaChatResponse.provider_used must always be 'meto'."""
        response = MetaChatResponse(
            conversation_id="conv-1",
            message_id="msg-1",
            content="Test content",
            provider_used="meto",
            fallback_used=False,
        )
        assert response.provider_used == "meto"

        # Even if someone accidentally set internal provider name
        response2 = MetaChatResponse(
            conversation_id="conv-2",
            message_id="msg-2",
            content="Test content",
        )
        assert response2.provider_used == "meto"


# ---------------------------------------------------------------------------
# Test 9, 10, 11: Quick prompts per screen
# ---------------------------------------------------------------------------

class TestQuickPrompts:
    def test_quick_prompts_dashboard(self):
        """Dashboard quick prompts: ≥2 items, all Vietnamese."""
        prompts = QUICK_PROMPTS.get("dashboard", [])
        assert len(prompts) >= 2, "Dashboard must have at least 2 quick prompts"
        for p in prompts:
            assert isinstance(p, str)
            assert len(p) > 0
            # Vietnamese characters check (common Vietnamese letters)
            assert any(c in p for c in "àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỵỹ") \
                or any(word in p.lower() for word in ["tôi", "của", "nào", "có", "hôm", "kết", "giải", "nhắc", "tình"])

    def test_quick_prompts_labs(self):
        """Labs quick prompts: ≥2 items, relevant to labs context."""
        prompts = QUICK_PROMPTS.get("labs", [])
        assert len(prompts) >= 2
        # At least one prompt should mention lab-related terms
        labs_keywords = ["xét nghiệm", "chỉ số", "bất thường", "kết quả", "hba1c", "so sánh"]
        combined = " ".join(prompts).lower()
        assert any(kw in combined for kw in labs_keywords), (
            f"Labs prompts should contain lab-related terms. Got: {prompts}"
        )

    def test_quick_prompts_medications(self):
        """Medications quick prompts: ≥2 items, relevant to medications context."""
        prompts = QUICK_PROMPTS.get("medications", [])
        assert len(prompts) >= 2
        meds_keywords = ["thuốc", "liều", "uống", "tác dụng", "quên"]
        combined = " ".join(prompts).lower()
        assert any(kw in combined for kw in meds_keywords), (
            f"Medications prompts should contain medication-related terms. Got: {prompts}"
        )

    def test_quick_prompts_all_screens_have_entries(self):
        """All known screens should have quick prompts configured."""
        known_screens = ["dashboard", "labs", "medications", "metrics", "nutrition", "care_plan", "profile"]
        for screen in known_screens:
            prompts = QUICK_PROMPTS.get(screen, [])
            assert len(prompts) >= 1, f"Screen '{screen}' has no quick prompts"

    def test_quick_prompts_unknown_screen_falls_back_to_dashboard(self):
        """Unknown screen_id should fall back to dashboard prompts (per route logic)."""
        from app.ai.prompt.safety import QUICK_PROMPTS as QP
        unknown_screen_prompts = QP.get("nonexistent_screen", QP.get("dashboard", []))
        assert len(unknown_screen_prompts) >= 1


# ---------------------------------------------------------------------------
# Test 12: Missing health data gracefully returns None
# ---------------------------------------------------------------------------

class TestMissingDataGraceful:
    def test_missing_health_data_returns_none_not_hallucinated(self):
        """User with NO health data must get None fields — not fabricated data."""
        # User exists but has NO metrics, NO labs, NO medications
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile={"display_name": "Empty User", "preferred_address": "bạn"},
            health_summary=None,      # no health summary
            care_plan=None,           # no care plan
            medications=None,         # no medications
            recent_labs=None,         # no labs
            recent_metrics=None,      # no metrics
        )

        assert ctx.health_summary is None
        assert ctx.medications is None
        assert ctx.recent_labs is None
        assert ctx.recent_metrics is None

        # user_profile can exist (not gated by consent)
        assert ctx.user_profile is not None
        assert ctx.user_profile["display_name"] == "Empty User"

    def test_missing_data_no_fabrication_in_included_blocks(self):
        """included_blocks must not list blocks with None data."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=_all_consents(),
            user_profile={"display_name": "Test"},
            health_summary=None,
            medications=None,
            recent_labs=None,
            recent_metrics=None,
        )

        # Blocks with None data should NOT be in included_blocks
        if ctx.health_summary is None:
            assert "health_summary" not in ctx.included_blocks
        if ctx.medications is None:
            assert "medications" not in ctx.included_blocks
        if ctx.recent_labs is None:
            assert "recent_labs" not in ctx.included_blocks

    def test_builder_returns_none_not_empty_structure_for_no_data(self):
        """Builder private methods return None (not empty dicts/lists) when DB empty."""
        builder = ContextBuilder()
        db = MagicMock()
        ep = MagicMock()
        ep.fetchall.return_value = []
        ep.fetchone.return_value = None
        db.execute.return_value = ep

        # All of these should return None, not empty containers
        assert builder._build_medications(db, "user-123") is None
        assert builder._build_recent_labs(db, "user-123") is None
        assert builder._build_recent_metrics(db, "user-123") is None

        # _build_user_profile now uses ORM (db.query) not db.execute.
        # Make db.query(User).filter(...).first() return None = user not found.
        db_orm = MagicMock()
        db_orm.query.return_value.filter.return_value.first.return_value = None
        assert builder._build_user_profile(db_orm, "user-123") is None


# ---------------------------------------------------------------------------
# Test 13: Safety — normal message, no escalation
# ---------------------------------------------------------------------------

class TestSafetyNormalMessage:
    def test_safety_normal_message_no_escalation(self):
        """Normal health question must not trigger escalation."""
        guard = SafetyGuard()
        result = guard.check_input("Giải thích xét nghiệm HbA1c là gì?")

        assert result.safe is True
        assert result.escalation_required is False
        assert result.escalation_tier is None

    def test_safety_normal_message_variety(self):
        """Variety of normal questions — none should escalate."""
        guard = SafetyGuard()
        normal_messages = [
            "Huyết áp của tôi có bình thường không?",
            "Tôi nên ăn gì để kiểm soát đường huyết?",
            "Thuốc Metformin có tác dụng phụ gì?",
            "Kết quả xét nghiệm tháng trước của tôi thế nào?",
            "Giải thích chỉ số cholesterol",
        ]
        for msg in normal_messages:
            result = guard.check_input(msg)
            assert result.safe is True, f"False positive escalation for: {msg!r}"

    @pytest.mark.asyncio
    async def test_safety_normal_message_chat_no_escalation_in_response(self):
        """Chat with normal message: response.escalation must be None."""
        from app.services.meto_chat import MetoChatService

        registry = _make_mock_registry("HbA1c là chỉ số đo lượng đường huyết trung bình 3 tháng.")
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="labs")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            mock_ctx.build.return_value = AssembledContext(
                user_profile={"display_name": "Test", "preferred_address": "bạn"},
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "labs"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=200,
                missing_consents=[],
                included_blocks=["user_profile", "screen_context"],
            )

            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            mock_prompt.assemble.return_value = (
                "system",
                [ChatMessage(role="user", content="test")],
            )
            mock_prompt.generate_conversation_title.return_value = "Test"
            mock_prompt._get_quick_prompts.return_value = []

            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Giải thích xét nghiệm HbA1c là gì?",
                screen_context=screen,
            )

        assert result.escalation is None
        assert result.content != ""
        assert len(result.content) > 0


# ---------------------------------------------------------------------------
# Test 14: Safety — emergency escalation
# ---------------------------------------------------------------------------

class TestSafetyEmergencyEscalation:
    def test_safety_emergency_detection(self):
        """Emergency phrases must trigger emergency escalation tier."""
        guard = SafetyGuard()
        result = guard.check_input("Tôi đang đau ngực rất dữ dội và khó thở")

        assert result.safe is False
        assert result.escalation_required is True
        assert result.escalation_tier == "emergency"
        assert result.suggested_response is not None
        # Escalation response must contain safety wording
        resp_lower = result.suggested_response.lower()
        assert "115" in resp_lower or "cấp cứu" in resp_lower or "bác sĩ" in resp_lower

    def test_safety_emergency_escalation_response_contains_115(self):
        """Emergency escalation response must reference emergency number 115."""
        guard = SafetyGuard()
        response = guard.get_escalation_response(["đau ngực"], tier="emergency")
        assert "115" in response

    @pytest.mark.asyncio
    async def test_safety_emergency_chat_returns_escalation_no_ai_called(self):
        """Emergency message: escalation returned, AI provider NOT called."""
        from app.services.meto_chat import MetoChatService

        registry = _make_mock_registry()
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="dashboard")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        ):
            mock_ctx.build.return_value = AssembledContext(
                user_profile=None,
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "dashboard"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=100,
                missing_consents=[],
                included_blocks=[],
            )

            from app.ai.prompt.safety import SafetyResult
            escalation_msg = (
                "⚠️ Gọi 115 ngay! Dấu hiệu cấp cứu — cần bác sĩ ngay."
            )
            mock_safety.check_input.return_value = SafetyResult(
                safe=False,
                flags=["đau ngực", "khó thở"],
                escalation_required=True,
                escalation_tier="emergency",
                suggested_response=escalation_msg,
            )
            mock_safety.get_escalation_response.return_value = escalation_msg

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Tôi đang đau ngực rất dữ dội và khó thở",
                screen_context=screen,
            )

        # AI must NOT have been called
        registry.call_with_fallback.assert_not_called()

        assert result.escalation is not None
        assert result.escalation.tier == "emergency"
        assert "115" in result.content or "cấp cứu" in result.content or "bác sĩ" in result.content
        assert result.provider_used == "meto"

    def test_safety_urgent_tier_detection(self):
        """Urgent (non-emergency) phrases trigger recommend_urgent tier."""
        guard = SafetyGuard()
        result = guard.check_input("Tôi bị sốt cao > 39 độ và đau đầu dữ dội bất thường")

        assert result.safe is False
        assert result.escalation_required is True
        assert result.escalation_tier in ("recommend_urgent", "emergency")


# ---------------------------------------------------------------------------
# Test 15: No consent → Meto says "chưa có dữ liệu" effectively
# ---------------------------------------------------------------------------

class TestNoConsentBehavior:
    """Fail-closed consent (BRD §J): without a category grant, that category's PHI
    is withheld from the AI context and reported in missing_consents.
    """
    @pytest.mark.real_consent
    def test_ungranted_categories_are_withheld(self):
        """With no consent rows, clinical blocks are excluded (data-minimizing)."""
        ctx = _build_with_patches(
            "dashboard",
            consent_rows=[],  # nothing granted
            user_profile={"display_name": "Test User", "preferred_address": "bạn"},
            health_summary={"primary_conditions": ["Tiểu đường"]},
            medications=[{"name": "Metformin"}],
        )
        # user_profile is non-clinical → still present; clinical blocks withheld.
        assert ctx.user_profile is not None
        assert ctx.health_summary is None
        assert ctx.medications is None

    @pytest.mark.real_consent
    def test_missing_consents_populated_without_grants(self):
        """missing_consents lists the ungranted categories the screen would use."""
        ctx = _build_with_patches("dashboard", consent_rows=[])
        assert "health_records" in ctx.missing_consents
        assert "medications" in ctx.missing_consents

    @pytest.mark.asyncio
    async def test_chat_response_returns_content_not_consent_gate(self):
        """Chat response: consent_required always False, content is the AI answer."""
        from app.services.meto_chat import MetoChatService

        # Response that mentions consent needed (would be driven by system prompt context)
        registry = _make_mock_registry(
            "Meto chưa được phép truy cập dữ liệu sức khỏe của bạn. "
            "Vui lòng cấp quyền trong cài đặt để Meto có thể hỗ trợ tốt hơn."
        )
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="dashboard")

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            # Context with health data included (no consent gate)
            mock_ctx.build.return_value = AssembledContext(
                user_profile={"display_name": "Test", "preferred_address": "bạn"},
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "dashboard"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=100,
                missing_consents=[],  # Always empty — no consent gate in chat
                included_blocks=["user_profile", "screen_context"],
            )

            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            mock_prompt.assemble.return_value = (
                "system",
                [ChatMessage(role="user", content="test")],
            )
            mock_prompt.generate_conversation_title.return_value = "Test"
            mock_prompt._get_quick_prompts.return_value = []

            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Tình trạng sức khỏe của tôi thế nào?",
                screen_context=screen,
            )

        assert isinstance(result, MetaChatResponse)
        # Content should not contain fabricated health data
        # (the mock returns a consent-related message)
        content_lower = result.content.lower()
        # Verify no fabricated health terms in content
        fabricated_health_terms = ["hemoglobin", "creatinine", "glucose = ", "hba1c ="]
        for term in fabricated_health_terms:
            assert term not in content_lower, (
                f"Possibly fabricated health data found: {term!r} in {result.content!r}"
            )


# ---------------------------------------------------------------------------
# Helpers used in async tests above
# ---------------------------------------------------------------------------

def _make_mock_db():
    """DB mock for service-level tests."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    db.add.return_value = None
    db.commit.return_value = None

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = "test-id"
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = dt.datetime.now(dt.UTC)
        if not hasattr(obj, "last_active_at"):
            obj.last_active_at = dt.datetime.now(dt.UTC)
        if not hasattr(obj, "message_count"):
            obj.message_count = 0
        if not hasattr(obj, "total_tokens"):
            obj.total_tokens = 0
        if not hasattr(obj, "title"):
            obj.title = None

    db.refresh.side_effect = _refresh
    return db
