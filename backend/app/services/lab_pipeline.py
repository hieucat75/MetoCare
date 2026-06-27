"""Async lab-document pipeline (P2 #3).

Replaces the synchronous mock interpret with a queue-driven pipeline:

    upload -> enqueue -> OCR -> parse -> normalize biomarkers -> store LabResult
            -> audit -> notify user

State machine on ``LabDocument.status``:

    uploaded -> ocr_pending -> ocr_done -> interpreted
                     |             |
                     v             v
                 ocr_failed   interpretation_failed   (both retryable -> ocr_pending)

The queue is a built-in asyncio.Queue drained by a worker task started in the
FastAPI lifespan (no Celery/RQ/Redis). Enqueue is idempotent: a document already
in-flight or already interpreted is a no-op. ``process_document`` is synchronous
and self-contained so it is unit-testable without a running event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domain import lab_interpreter
from app.models.clinical import LabDocument, LabResult
from app.models.patient import PatientProfile
from app.services import audit, notifications
from app.services.lab import normalize_and_classify
from app.services.ocr import OCRError, get_ocr_provider

logger = logging.getLogger("mcp.lab_pipeline")


class LabDocStatus(StrEnum):
    UPLOADED = "uploaded"
    OCR_PENDING = "ocr_pending"
    OCR_DONE = "ocr_done"
    OCR_FAILED = "ocr_failed"
    INTERPRETED = "interpreted"
    INTERPRETATION_FAILED = "interpretation_failed"


class InvalidTransition(ValueError):
    """Raised when an illegal state-machine transition is attempted."""


_ALLOWED: dict[LabDocStatus, set[LabDocStatus]] = {
    LabDocStatus.UPLOADED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.OCR_PENDING: {LabDocStatus.OCR_DONE, LabDocStatus.OCR_FAILED},
    LabDocStatus.OCR_DONE: {LabDocStatus.INTERPRETED, LabDocStatus.INTERPRETATION_FAILED},
    LabDocStatus.OCR_FAILED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.INTERPRETATION_FAILED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.INTERPRETED: set(),
}

# A document can (re-)enter the queue only from these states.
_ENQUEUEABLE = {
    LabDocStatus.UPLOADED,
    LabDocStatus.OCR_FAILED,
    LabDocStatus.INTERPRETATION_FAILED,
}


def _transition(doc: LabDocument, new: LabDocStatus) -> None:
    current = LabDocStatus(doc.status)
    if new not in _ALLOWED[current]:
        raise InvalidTransition(f"{current} -> {new} is not allowed")
    doc.status = new.value


def _patient_user_id(db: Session, patient_id: str) -> str:
    profile = db.get(PatientProfile, patient_id)
    return profile.user_id if profile and profile.user_id else patient_id


# --------------------------------------------------------------------------- #
# Pipeline core (synchronous, self-contained, unit-testable)
# --------------------------------------------------------------------------- #

def process_document(db: Session, *, document_id: str) -> LabDocument | None:
    """Run OCR + interpretation for a document that is in OCR_PENDING.

    Idempotent: a document not in OCR_PENDING is left untouched (returns it). All
    failures move the document to a terminal failed state + audit (never raise to
    the worker loop)."""
    doc = db.get(LabDocument, document_id)
    if doc is None:
        return None
    if doc.status != LabDocStatus.OCR_PENDING.value:
        return doc  # already processed / not enqueued -> no-op

    user_id = _patient_user_id(db, doc.patient_id)

    # ---- OCR ----
    try:
        extraction = get_ocr_provider().extract(doc.storage_key)
    except OCRError as exc:
        _transition(doc, LabDocStatus.OCR_FAILED)
        doc.ocr_status = "failed"
        audit.record(
            db,
            actor_type="system",
            actor_id="ocr_worker",
            action="ocr_extract",
            resource_type="lab_document",
            resource_id=doc.id,
            outcome="failure",
            severity="warning",
        )
        db.commit()
        notifications.notify(user_id, "lab_ocr_failed", document_id=doc.id)
        logger.warning("ocr_failed document_id=%s: %s", doc.id, exc)
        return doc

    doc.raw_text = extraction.text
    _transition(doc, LabDocStatus.OCR_DONE)
    doc.ocr_status = "done"
    db.flush()

    # ---- Interpretation + normalized LabResult rows ----
    try:
        interpretation = lab_interpreter.interpret_panel(extraction.values)
        new_rows: list[LabResult] = []
        for b in interpretation.biomarkers:
            # ── P0 Safety gate ───────────────────────────────────────────────────
            # Rows that carry a suspect machine-model number as value (e.g.
            # "502" from Cobas C502) are already excluded from interpretation.biomarkers
            # by map_table_rows_to_raw_values().  However the same gate applies
            # here at the pipeline level as a defence-in-depth check on the
            # RawLabValue that was passed in via extraction.values (text-parser
            # path also flows through here):
            #
            # A biomarker is blocked from auto-save when:
            #   - ocr_confidence < 0.5       (not reliable enough)
            #   - needs_verification = True  (missing unit, impossible value, etc.)
            #   - raw value has suspect_machine_id flag
            #
            # Blocked rows are stored with verified_by_user=False so the review
            # UI can show them for explicit user confirmation.
            raw: lab_interpreter.RawLabValue | None = next(
                (v for v in extraction.values if v.test_name == b.canonical), None
            )
            suspect = getattr(raw, "suspect_machine_id", False) if raw else False
            requires_review = getattr(raw, "requires_review", False) if raw else False
            auto_save_blocked = (
                suspect
                or requires_review
                or b.ocr_confidence < 0.5
                or b.needs_verification
            )
            if auto_save_blocked:
                logger.warning(
                    "lab_pipeline_review_required document_id=%s canonical=%s "
                    "confidence=%.2f suspect=%s requires_review=%s",
                    doc.id, b.canonical, b.ocr_confidence, suspect, requires_review,
                )
            # Auto-classify + normalize at creation time.
            _clf = normalize_and_classify(b.canonical, b.value, b.unit or "")
            _status = _clf.get("status") if _clf else None
            # Fallback to interpreter status when canonical classification succeeds.
            if _status is None and b.status.value not in ("unknown",):
                _status = b.status.value

            lr = LabResult(
                patient_id=doc.patient_id,
                document_id=doc.id,
                test_name=b.raw_name,
                canonical_name=b.canonical,
                value=b.value,
                unit=b.unit,
                reference_range=b.reference_range,
                status=_status,
                ocr_confidence=b.ocr_confidence,
                # verified_by_user=False means the row awaits explicit user confirmation.
                verified_by_user=not auto_save_blocked,
                normalized_value_si=_clf.get("normalized_value_si") if _clf else None,
                normalized_unit_si=_clf.get("normalized_unit_si") if _clf else None,
            )
            db.add(lr)
            new_rows.append(lr)
        db.flush()
        # Promote into health_metrics so the dashboard + trends reflect these results.
        # FU-1 safety gate: only promote rows explicitly confirmed by the user.
        # Rows with verified_by_user=False (suspect_machine_id, low confidence,
        # missing unit, needs_verification) remain as LabResult records available
        # in the review UI but must NOT enter patient metrics/dashboard until confirmed.
        from app.services.lab import promote_lab_rows_to_metrics
        verified_rows = [r for r in new_rows if r.verified_by_user]
        if len(verified_rows) < len(new_rows):
            logger.warning(
                "lab_pipeline_promote_gate document_id=%s total=%d verified=%d blocked=%d",
                doc.id, len(new_rows), len(verified_rows), len(new_rows) - len(verified_rows),
            )
        promote_lab_rows_to_metrics(db, patient_id=doc.patient_id, rows=verified_rows, test_date=None)  # noqa: E501
        _transition(doc, LabDocStatus.INTERPRETED)
    except Exception as exc:  # interpretation must never crash the worker
        _transition(doc, LabDocStatus.INTERPRETATION_FAILED)
        audit.record(
            db,
            actor_type="system",
            actor_id="ocr_worker",
            action="interpret",
            resource_type="lab_document",
            resource_id=doc.id,
            outcome="failure",
            severity="warning",
        )
        db.commit()
        notifications.notify(user_id, "lab_interpretation_failed", document_id=doc.id)
        logger.warning("interpretation_failed document_id=%s: %s", doc.id, exc)
        return doc

    audit.record(
        db,
        actor_type="system",
        actor_id="ocr_worker",
        action="interpret",
        resource_type="lab_document",
        resource_id=doc.id,
        outcome="success",
    )
    db.commit()
    notifications.notify(user_id, "lab_interpreted", document_id=doc.id)
    return doc


# --------------------------------------------------------------------------- #
# Worker manager: idempotent enqueue + asyncio queue + drain
# --------------------------------------------------------------------------- #

class OCRWorkerManager:
    def __init__(self) -> None:
        self._inflight: set[str] = set()
        self._buffer: list[str] = []  # ids waiting to be processed
        self._lock = threading.Lock()
        self._event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._stop = False
        self.processed_count = 0

    # ---- enqueue (sync, idempotent) ----
    def enqueue(self, db: Session, *, document_id: str, requester_id: str) -> bool:
        """Transition a document to OCR_PENDING and queue it. No-op (False) if the
        document is missing, already in-flight, or already interpreted."""
        doc = db.get(LabDocument, document_id)
        if doc is None:
            return False
        if LabDocStatus(doc.status) not in _ENQUEUEABLE:
            return False
        with self._lock:
            if document_id in self._inflight:
                return False
            self._inflight.add(document_id)
            self._buffer.append(document_id)

        _transition(doc, LabDocStatus.OCR_PENDING)
        doc.ocr_status = "pending"
        audit.record(
            db,
            actor_type="user",
            actor_id=requester_id,
            action="ocr_enqueue",
            resource_type="lab_document",
            resource_id=document_id,
        )
        db.commit()
        if self._event is not None:
            self._event.set()
        return True

    def pending(self) -> int:
        with self._lock:
            return len(self._buffer)

    def _pop(self) -> str | None:
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer.pop(0)

    def _release(self, document_id: str) -> None:
        with self._lock:
            self._inflight.discard(document_id)

    # ---- drain one (sync; opens its own session) ----
    def process_next(self) -> str | None:
        document_id = self._pop()
        if document_id is None:
            return None
        db = SessionLocal()
        try:
            process_document(db, document_id=document_id)
        finally:
            db.close()
            self._release(document_id)
            self.processed_count += 1
        return document_id

    def drain(self) -> int:
        """Process the whole buffer synchronously (tests / shutdown flush)."""
        n = 0
        while self.process_next() is not None:
            n += 1
        return n

    # ---- async worker (started in lifespan) ----
    async def run(self) -> None:
        self._event = asyncio.Event()
        self._stop = False
        loop = asyncio.get_running_loop()
        while not self._stop:
            if self.pending() == 0:
                self._event.clear()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=0.5)
                except TimeoutError:
                    continue
            # Offload the (blocking) sync DB work to a thread.
            await loop.run_in_executor(None, self.process_next)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop = True
        if self._event is not None:
            self._event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=1.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    def reset(self) -> None:
        with self._lock:
            self._inflight.clear()
            self._buffer.clear()
        self.processed_count = 0


_manager = OCRWorkerManager()


def get_worker() -> OCRWorkerManager:
    return _manager
