"""BR-F5 — `POST /documents/{id}/reprocess` must degrade honestly when the
backing blob is gone.

`ObjectNotFound` subclasses `StorageError`, not `MdiError`, so the route's
`except mdi.MdiError` handler never saw it and the request became an opaque
HTTP 500. With ephemeral container storage (PROD-F1) a missing blob is an
*expected* state after any redeploy, so this is the failure mode most likely to
be hit in the pilot.
"""

from __future__ import annotations

import pytest
from app.api.v1.routes.documents import _map_mdi_error
from app.models.medical_document import (
    DOC_STATUS_NEEDS_REVIEW,
    OBJECT_STATE_ACCEPTED,
    MedicalDocument,
)
from app.services.mdi import service as mdi
from app.services.storage import ObjectNotFound


@pytest.fixture
def accepted_doc_with_missing_blob(db, patient):
    doc = MedicalDocument(
        patient_id=patient["patient_id"],
        quarantine_key="quarantine/does-not-exist/202608/deadbeef.jpg",
        accepted_key="accepted/does-not-exist/202608/deadbeef.jpg",
        mime="image/jpeg",
        status=DOC_STATUS_NEEDS_REVIEW,
        object_state=OBJECT_STATE_ACCEPTED,
        scan_status="clean",
    )
    db.add(doc)
    db.commit()
    yield doc
    db.delete(doc)
    db.commit()


def test_reprocess_missing_blob_raises_a_handled_mdi_error(
    db, patient, accepted_doc_with_missing_blob
):
    with pytest.raises(mdi.MdiError) as excinfo:
        mdi.reprocess_document(
            db, patient_id=patient["patient_id"], document_id=accepted_doc_with_missing_blob.id
        )
    # The raw storage error must not escape the service boundary.
    assert not isinstance(excinfo.value, ObjectNotFound)
    assert str(excinfo.value), "the error must carry an honest, user-facing message"


def test_reprocess_missing_blob_maps_to_a_4xx_not_a_500(
    db, patient, accepted_doc_with_missing_blob
):
    with pytest.raises(mdi.MdiError) as excinfo:
        mdi.reprocess_document(
            db, patient_id=patient["patient_id"], document_id=accepted_doc_with_missing_blob.id
        )
    http_exc = _map_mdi_error(excinfo.value)
    assert 400 <= http_exc.status_code < 500
