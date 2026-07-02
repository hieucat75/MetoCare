"""P0 regression: Meto AI must load latest lab results from the DB into context.

Root cause guarded here: clinical data (lab_upload_batches / lab_results) is keyed
by ``patient_profiles.id``, but the ContextBuilder historically filtered by
``user.id``. Since ``profile.id != user.id``, the labs never matched and Meto
would answer "không có xét nghiệm" even when the DB had data — a P0.

This test seeds a real patient + a cardiovascular lipid panel (LDL, HDL, HbA1c)
and asserts:
  1. The assembled context (dashboard screen — the default CV-risk entry point)
     contains all 3 lab results with full fields.
  2. The prompt the LLM actually receives embeds those 3 results, so the model
     is given the data and cannot ask the patient to re-upload.
"""
from __future__ import annotations

import datetime as dt

from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import ScreenContext
from app.ai.prompt.assembler import PromptAssembler
from app.models.clinical import LabResult, LabUploadBatch
from app.utils.number_format import format_lab_value

# Cardiovascular lipid/glycemic panel — (test_name, value, unit, reference_range, status)
_CARDIO_PANEL = [
    ("LDL Cholesterol", 180.0, "mg/dL", "< 100", "high"),
    ("HDL Cholesterol", 32.0, "mg/dL", "> 40", "low"),
    ("HbA1c", 7.8, "%", "< 5.7", "high"),
]


def _seed_cardio_labs(db, profile_id: str) -> str:
    """Seed one batch + the 3 cardio labs keyed by profile_id (as the app stores them)."""
    batch = LabUploadBatch(
        patient_id=profile_id,
        lab_name="Xét nghiệm mỡ máu",
        test_date=dt.date.today(),
    )
    db.add(batch)
    db.flush()

    for name, value, unit, ref, status in _CARDIO_PANEL:
        db.add(
            LabResult(
                patient_id=profile_id,
                batch_id=batch.id,
                test_name=name,
                value=value,
                unit=unit,
                reference_range=ref,
                status=status,
                test_date=dt.date.today(),
            )
        )
    db.commit()
    return batch.id


def test_cardio_chat_context_includes_seeded_labs(db, patient):
    """Seed LDL/HDL/HbA1c → context (dashboard screen) must expose all 3 with full fields."""
    user_id = patient["user_id"]
    profile_id = patient["patient_id"]

    try:
        _seed_cardio_labs(db, profile_id)

        # "dashboard" is MetoChatRequest's default screen — the realistic entry
        # point when a patient asks about cardiovascular risk from the home tab.
        ctx = ContextBuilder().build(db, user_id, ScreenContext(screen_id="dashboard"))

        # P0: labs must be loaded from the DB, NOT None.
        assert ctx.recent_labs is not None, (
            "P0 REGRESSION: recent_labs is None although the DB has 3 lab results"
        )
        assert len(ctx.recent_labs) == 3, f"expected 3 labs, got {len(ctx.recent_labs)}"

        by_name = {lab["test_name"]: lab for lab in ctx.recent_labs}
        assert set(by_name) == {"LDL Cholesterol", "HDL Cholesterol", "HbA1c"}

        # Full field coverage: metric, value, unit, status, reference range, collected_at.
        # value is the ORIGINAL formatted via format_lab_value (e.g. 180.0 → "180").
        for name, value, unit, ref, status in _CARDIO_PANEL:
            lab = by_name[name]
            assert lab["value"] == format_lab_value(value, unit)
            assert lab["unit"] == unit
            assert lab["reference_range"] == ref
            assert lab["status"] == status
            assert lab["collected_date"] == dt.date.today().isoformat()

        assert "recent_labs" in ctx.included_blocks

    finally:
        db.query(LabResult).filter(LabResult.patient_id == profile_id).delete()
        db.query(LabUploadBatch).filter(LabUploadBatch.patient_id == profile_id).delete()
        db.commit()


def test_cardio_chat_prompt_embeds_labs_so_ai_wont_ask_reupload(db, patient):
    """The prompt sent to the LLM must embed the 3 labs → AI cannot ask to re-upload."""
    user_id = patient["user_id"]
    profile_id = patient["patient_id"]

    try:
        _seed_cardio_labs(db, profile_id)

        ctx = ContextBuilder().build(db, user_id, ScreenContext(screen_id="dashboard"))
        system_prompt, _messages = PromptAssembler().assemble(
            context=ctx,
            user_message="Đánh giá nguy cơ tim mạch",
            conversation_history=[],
        )

        # Every seeded lab must appear in the prompt the model receives.
        for name, value, _unit, _ref, _status in _CARDIO_PANEL:
            assert name in system_prompt, f"{name} missing from prompt — AI is blind to it"
            assert (
                format_lab_value(value, _unit) in system_prompt
            ), f"value for {name} missing from prompt"

        # The labs section header must be present (assembler renders recent_labs).
        assert "Kết quả xét nghiệm" in system_prompt

    finally:
        db.query(LabResult).filter(LabResult.patient_id == profile_id).delete()
        db.query(LabUploadBatch).filter(LabUploadBatch.patient_id == profile_id).delete()
        db.commit()
