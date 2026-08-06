"""Unit tests for the Journey-2/3 health-timeline extensions (BRD §H):
medication dose events + medical-document / confirmed-candidate events."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app.domain.health_timeline import HealthTimelineEngine


def _eng():
    return HealthTimelineEngine()


def test_dose_document_and_confirmed_candidate_events_included():
    doses = [
        SimpleNamespace(
            id="d1",
            state="taken",
            acted_at=dt.datetime(2026, 6, 1, 8, 0),
            scheduled_utc=dt.datetime(2026, 6, 1, 8, 0),
            schedule_id="s1",
            local_render="2026-06-01 08:00",
        )
    ]
    docs = [
        SimpleNamespace(
            id="doc1",
            doc_type="prescription",
            status="confirmed",
            created_at=dt.datetime(2026, 6, 1, 7, 0),
        )
    ]
    cands = [
        SimpleNamespace(
            id="c1",
            candidate_type="diagnosis",
            reviewed_at=dt.datetime(2026, 6, 1, 7, 30),
            created_at=None,
            fields_json={"text": "Tăng huyết áp"},
            document_id="doc1",
        )
    ]
    events = _eng().build(
        lab_batches=[], lab_results=[], health_metrics=[], medications=[], symptom_logs=[],
        dose_occurrences=doses, documents=docs, confirmed_candidates=cands,
    )
    types = {e.event_type for e in events}
    assert "medication_dose_taken" in types
    assert "document_uploaded" in types
    assert "confirmed_diagnosis" in types
    cand_ev = next(e for e in events if e.event_type == "confirmed_diagnosis")
    assert cand_ev.metadata["document_id"] == "doc1"  # provenance backlink


def test_pending_dose_not_in_timeline():
    doses = [
        SimpleNamespace(
            id="d2", state="pending", acted_at=None,
            scheduled_utc=dt.datetime(2026, 6, 1, 8, 0), schedule_id="s1", local_render="",
        )
    ]
    events = _eng().build(
        lab_batches=[], lab_results=[], health_metrics=[], medications=[], symptom_logs=[],
        dose_occurrences=doses,
    )
    assert not any(e.source == "medication_dose" for e in events)


def test_backward_compatible_without_new_sources():
    events = _eng().build(
        lab_batches=[], lab_results=[], health_metrics=[], medications=[], symptom_logs=[]
    )
    assert events == []  # no data, no new params → no events, no crash
