"""P1-4 — a context block that FAILED must not look like a block that was EMPTY.

Every block builder in `ContextBuilder` wrapped its query in `except Exception`,
logged a warning, and returned `None`. `None` is also what a block holds when the
patient consented but genuinely has no rows. So a transient failure of the labs
query produced a context identical to a healthy patient's, and because
`safety_flags` is *derived* from `recent_labs` / `recent_metrics`, the flag list
came back empty too. Meto then answered a patient who may have had a CRITICAL
potassium on file as though nothing was abnormal.

Absence of evidence rendered as evidence of absence, to a patient, by a health
assistant. There was no signal anywhere in `AssembledContext` that anything had
gone wrong — `missing_consents` covers a declined block, which is a different
statement, and one the model can reason about correctly.

Reachability is not hypothetical. SEC-F11 sets `on_decrypt_failure="raise"`, so a
single unreadable ciphertext now RAISES inside these builders rather than
yielding None. Hardening the crypto made this path *easier* to reach — correctly,
since the wrong response to unreadable PHI is to proceed silently.

The fix records failures in `degraded_blocks`, and the prompt assembler turns a
non-empty list into a prohibition on asserting absence — phrased as a
prohibition rather than a disclosure, because a disclosure the model may
paraphrase away does not protect the patient.
"""

from __future__ import annotations

import pytest
from app.ai.context.schemas import AssembledContext
from app.ai.prompt.assembler import _format_context_block

SAFETY_CRITICAL = ("recent_labs", "recent_metrics", "medications", "health_summary")


def _builder():
    from app.ai.context.builder import ContextBuilder

    return ContextBuilder()


# ── 1. The contract: failed and empty are different states ──────────────────


def test_empty_context_reports_no_degradation():
    ctx = AssembledContext()
    assert ctx.degraded_blocks == []
    assert ctx.has_safety_critical_degradation() is False


@pytest.mark.parametrize("block", SAFETY_CRITICAL)
def test_safety_critical_blocks_are_recognised(block):
    ctx = AssembledContext(degraded_blocks=[block])
    assert ctx.has_safety_critical_degradation() is True


def test_a_non_clinical_block_failure_is_not_safety_critical():
    """user_profile failing is a degraded experience, not a safety event — the
    distinction has to be real or the warning becomes noise."""
    ctx = AssembledContext(degraded_blocks=["user_profile"])
    assert ctx.degraded_blocks == ["user_profile"]
    assert ctx.has_safety_critical_degradation() is False


# ── 2. The prompt must say so, and must forbid asserting absence ────────────


def test_prompt_is_silent_when_nothing_degraded():
    text = _format_context_block(AssembledContext(user_profile={"display_name": "A"}))
    assert "KHÔNG TẢI ĐƯỢC" not in text


@pytest.mark.parametrize("block", SAFETY_CRITICAL)
def test_prompt_forbids_reassurance_when_a_clinical_block_failed(block):
    text = _format_context_block(AssembledContext(degraded_blocks=[block]))

    assert "KHÔNG TẢI ĐƯỢC" in text
    assert block in text
    # It must not be reported as "the user has no data".
    assert "KHÔNG phải là" in text
    # And the model must be told not to conclude the patient is fine.
    assert "không được kết luận" in text.lower()
    assert "không trấn an" in text.lower()


def test_prompt_warns_without_the_reassurance_clause_for_a_non_clinical_block():
    text = _format_context_block(AssembledContext(degraded_blocks=["user_profile"]))
    assert "KHÔNG TẢI ĐƯỢC" in text
    assert "không trấn an" not in text.lower()


def test_degradation_notice_precedes_the_consent_notice():
    """They are different statements and the order matters: 'we could not read
    your data' must not be buried under 'you declined to share data'."""
    text = _format_context_block(
        AssembledContext(degraded_blocks=["recent_labs"], missing_consents=["labs"])
    )
    assert text.index("KHÔNG TẢI ĐƯỢC") < text.index("quyền riêng tư")


def test_every_degraded_block_is_named():
    text = _format_context_block(
        AssembledContext(degraded_blocks=["recent_labs", "medications"])
    )
    assert "recent_labs" in text
    assert "medications" in text


# ── 3. The builders record failures rather than swallowing them ─────────────


def test_builders_still_work_without_a_sink(db, patient):
    """The sink is optional so a builder can be called in isolation; `build()`
    always passes one. Pin that the optionality did not become a way to lose
    failures on the real path."""
    assert _builder()._build_user_profile(db, patient["user_id"]) is not None


def test_a_raising_query_is_recorded_in_the_sink(db):
    """The regression itself, exercised through the real handler: a builder whose
    query raises must return None AND name itself as degraded."""
    builder = _builder()
    sink: list[str] = []
    # A user id that is not a valid row forces the ORM/decrypt path to fail or
    # return nothing; drive the handler directly with a broken session instead so
    # the exception is unambiguous.

    class _BrokenSession:
        def execute(self, *a, **k):
            raise RuntimeError("simulated decrypt/DB failure")

        def query(self, *a, **k):
            raise RuntimeError("simulated decrypt/DB failure")

        def get(self, *a, **k):
            raise RuntimeError("simulated decrypt/DB failure")

        def rollback(self):
            pass

    result = builder._build_recent_labs(_BrokenSession(), "any-user", sink)

    assert result is None, "a failing builder must not fabricate data"
    assert sink == ["recent_labs"], "the failure was swallowed instead of recorded"


def test_a_failed_clinical_block_reaches_the_prompt_as_a_prohibition(db):
    """End-to-end shape: sink -> AssembledContext -> prompt text."""
    builder = _builder()
    sink: list[str] = []

    class _BrokenSession:
        def execute(self, *a, **k):
            raise RuntimeError("boom")

        def query(self, *a, **k):
            raise RuntimeError("boom")

        def rollback(self):
            pass

    builder._build_recent_labs(_BrokenSession(), "any-user", sink)
    text = _format_context_block(AssembledContext(degraded_blocks=sink))

    assert "recent_labs" in text
    assert "không trấn an" in text.lower()


def test_build_threads_a_sink_into_every_clinical_builder():
    """Source-level guard: a new block builder that forgets the sink would
    silently reintroduce the class."""
    import inspect

    from app.ai.context import builder as builder_mod

    src = inspect.getsource(builder_mod.ContextBuilder.build)
    for name in ("user_profile", "health_summary", "care_plan",
                 "medications", "recent_labs", "recent_metrics"):
        assert f"_build_{name}(db, user_id, degraded)" in src, (
            f"_build_{name} is not passed the degradation sink in build()"
        )
    assert "degraded_blocks=degraded" in src
