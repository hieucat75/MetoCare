"""PRIV-F5 — GDPR erasure must reach the PHI-bearing *child* rows.

`delete_account` used to stamp only the parents (`MetoConversation`,
`MedicalDocument`) and leave the rows that actually hold the text intact:
`MetoMessage.content`, `DocumentPage.ocr_raw`/`blocks_json`,
`ExtractionCandidate.fields_json`/`corrections_json`. Since the export bundle
deliberately omits message content, that data was neither exportable nor
erasable — the worst possible combination for a data-subject request.

`test_no_phi_column_on_a_child_table_survives_erasure` is the regression that
matters: it enumerates the free-text / JSON columns of each child table from the
ORM metadata rather than from a hand-written list, so adding a new PHI column
without erasing it fails the suite.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.core.crypto import EncryptedString
from app.models.medical_document import (
    DOC_STATUS_NEEDS_REVIEW,
    OBJECT_STATE_ACCEPTED,
    DocumentExtraction,
    DocumentPage,
    ExtractionCandidate,
    MedicalDocument,
)
from app.models.meto import MetoConversation, MetoMessage
from app.services import account as account_svc
from sqlalchemy import JSON, Text
from sqlalchemy.orm import Session

# Child tables whose free-text / JSON columns hold patient-derived content.
_PHI_CHILD_MODELS = (MetoMessage, DocumentPage, ExtractionCandidate)

# Columns on those tables that are structurally *not* PHI: an opaque storage
# key (the blob it points at is deleted separately, and the key embeds only
# ids), and nothing else. Anything not listed here must be blanked by erasure.
_NON_PHI_COLUMNS = {("document_pages", "storage_key")}

_BLANK_VALUES = (None, "", {}, [])


def _phi_columns(model) -> list[str]:
    """Free-text / JSON columns on `model`, derived from the ORM metadata."""
    names = []
    for col in model.__table__.columns:
        if (model.__tablename__, col.name) in _NON_PHI_COLUMNS:
            continue
        if isinstance(col.type, EncryptedString | Text | JSON):
            names.append(col.name)
        elif col.type.__class__.__name__ in ("JSONB", "JSON"):
            names.append(col.name)
    return names


@pytest.fixture
def seeded_phi(db: Session, patient):
    """Seed one row in every PHI-bearing child table the patient owns."""
    uid, pid = patient["user_id"], patient["patient_id"]

    conv = MetoConversation(user_id=uid, status="active", title="Hỏi về đường huyết")
    db.add(conv)
    db.flush()
    msg = MetoMessage(
        conversation_id=conv.id,
        role="user",
        content="Tôi bị tiểu đường type 2, HbA1c 8.9, đang dùng Metformin 850mg",
        tool_calls=[{"name": "get_labs"}],
        tool_results=[{"hba1c": 8.9}],
    )
    db.add(msg)

    doc = MedicalDocument(
        patient_id=pid,
        quarantine_key=f"quarantine/{pid}/202608/erasure-test.jpg",
        accepted_key=f"accepted/{pid}/202608/erasure-test.jpg",
        mime="image/jpeg",
        status=DOC_STATUS_NEEDS_REVIEW,
        object_state=OBJECT_STATE_ACCEPTED,
        scan_status="clean",
    )
    db.add(doc)
    db.flush()
    page = DocumentPage(
        document_id=doc.id,
        page_no=1,
        storage_key=f"accepted/{pid}/202608/erasure-test-p1.jpg",
        ocr_raw="BỆNH VIỆN X — Nguyễn Văn A — Glucose 9.1 mmol/L",
        blocks_json={"lines": ["Glucose 9.1 mmol/L"]},
    )
    db.add(page)
    extraction = DocumentExtraction(
        document_id=doc.id,
        schema_version="1",
        provider="mock",
        extraction_run_id="erasure-test-run",
    )
    db.add(extraction)
    db.flush()
    candidate = ExtractionCandidate(
        extraction_id=extraction.id,
        document_id=doc.id,
        patient_id=pid,
        candidate_type="medication",
        fields_json={"name": "Metformin", "strength": "850mg"},
        field_confidence_json={"name": 0.93},
        corrections_json={"name": "Metformin STADA"},
        dedupe_key="medication|metformin|850mg",
    )
    db.add(candidate)
    db.commit()
    return {
        "user_id": uid,
        "patient_id": pid,
        "message_id": msg.id,
        "page_id": page.id,
        "candidate_id": candidate.id,
    }


def test_erasure_blanks_meto_message_bodies(db, seeded_phi):
    account_svc.delete_account(
        db, user_id=seeded_phi["user_id"], patient_id=seeded_phi["patient_id"]
    )
    db.commit()
    db.expire_all()
    msg = db.get(MetoMessage, seeded_phi["message_id"])
    assert msg is not None, "the row skeleton is retained (audit joins still resolve)"
    assert not msg.content
    assert msg.tool_calls is None
    assert msg.tool_results is None


def test_erasure_blanks_document_page_ocr_text(db, seeded_phi):
    account_svc.delete_account(
        db, user_id=seeded_phi["user_id"], patient_id=seeded_phi["patient_id"]
    )
    db.commit()
    db.expire_all()
    page = db.get(DocumentPage, seeded_phi["page_id"])
    assert page is not None
    assert page.ocr_raw is None
    assert page.blocks_json is None


def test_erasure_blanks_extraction_candidate_fields(db, seeded_phi):
    account_svc.delete_account(
        db, user_id=seeded_phi["user_id"], patient_id=seeded_phi["patient_id"]
    )
    db.commit()
    db.expire_all()
    cand = db.get(ExtractionCandidate, seeded_phi["candidate_id"])
    assert cand is not None
    assert not cand.fields_json
    assert cand.field_confidence_json is None
    assert cand.corrections_json is None


def test_erasure_is_idempotent(db, seeded_phi):
    for _ in range(2):
        account_svc.delete_account(
            db, user_id=seeded_phi["user_id"], patient_id=seeded_phi["patient_id"]
        )
        db.commit()
    db.expire_all()
    assert not db.get(MetoMessage, seeded_phi["message_id"]).content


def test_no_phi_column_on_a_child_table_survives_erasure(db, seeded_phi):
    """Metadata-driven: a PHI column added later without an erasure rule fails."""
    account_svc.delete_account(
        db, user_id=seeded_phi["user_id"], patient_id=seeded_phi["patient_id"]
    )
    db.commit()
    db.expire_all()

    rows = {
        MetoMessage: db.get(MetoMessage, seeded_phi["message_id"]),
        DocumentPage: db.get(DocumentPage, seeded_phi["page_id"]),
        ExtractionCandidate: db.get(ExtractionCandidate, seeded_phi["candidate_id"]),
    }
    leaked = []
    for model in _PHI_CHILD_MODELS:
        row = rows[model]
        for name in _phi_columns(model):
            value = getattr(row, name)
            if isinstance(value, dt.datetime):
                continue
            if value not in _BLANK_VALUES:
                leaked.append(f"{model.__tablename__}.{name}")
    assert not leaked, (
        "PHI survived GDPR erasure in "
        f"{leaked} — extend app/services/account.delete_account to blank it"
    )


def test_erasure_succeeds_for_a_patient_with_symptom_logs_and_no_ocr_candidates(db, patient):
    """Regression: two candidate-blanking lines were pasted into the symptom_logs
    loop, referencing the loop variable of an EARLIER loop. A patient who had
    logged a symptom but never uploaded a document has zero ExtractionCandidate
    rows, so that name was never bound and the whole GDPR deletion raised
    UnboundLocalError -> unhandled 500 -> nothing committed. Erasure failed
    entirely for a very ordinary account, while the compliance docs asserted it
    was complete."""
    from app.models.clinical import SymptomLog
    from app.models.medical_document import ExtractionCandidate
    from app.services import account as account_svc

    pid = patient["patient_id"]
    import datetime as _dt

    db.add(
        SymptomLog(
            patient_id=pid,
            description="Chóng mặt buổi sáng",
            reported_at=_dt.datetime.now(_dt.UTC),
        )
    )
    db.commit()

    assert (
        db.query(ExtractionCandidate).filter_by(patient_id=pid).count() == 0
    ), "fixture precondition: no OCR candidates"

    account_svc.delete_account(db, user_id=patient["user_id"], patient_id=pid)
    db.commit()

    assert db.query(SymptomLog).filter_by(patient_id=pid).one().description == ""
