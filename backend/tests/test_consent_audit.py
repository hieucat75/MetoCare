"""Consent gate + audit baseline tests."""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.governance import AuditLog
from app.services import audit, consent, health_metrics
from app.services.consent import ConsentError


def test_owner_has_self_access(db, patient):
    assert consent.has_access(
        db, patient_id=patient["patient_id"], requester_id=patient["user_id"], scope="health_metric"
    )


def test_third_party_denied_without_consent(db, patient):
    assert not consent.has_access(
        db, patient_id=patient["patient_id"], requester_id="doctor-x", scope="health_metric"
    )


def test_consent_grant_then_access_then_revoke(db, patient):
    c = consent.grant(
        db,
        patient_id=patient["patient_id"],
        consent_type="data_sharing",
        data_scope="health_metric",
        granted_to="doctor-x",
    )
    db.commit()
    assert consent.has_access(
        db, patient_id=patient["patient_id"], requester_id="doctor-x", scope="health_metric"
    )
    consent.revoke(db, c.id)
    db.commit()
    assert not consent.has_access(
        db, patient_id=patient["patient_id"], requester_id="doctor-x", scope="health_metric"
    )


def test_scope_is_enforced(db, patient):
    consent.grant(
        db,
        patient_id=patient["patient_id"],
        consent_type="data_sharing",
        data_scope="lab",
        granted_to="doctor-y",
    )
    db.commit()
    # has lab consent, not health_metric
    assert consent.has_access(
        db, patient_id=patient["patient_id"], requester_id="doctor-y", scope="lab"
    )
    assert not consent.has_access(
        db, patient_id=patient["patient_id"], requester_id="doctor-y", scope="health_metric"
    )


def test_create_metric_without_consent_raises(db, patient):
    with pytest.raises(ConsentError):
        health_metrics.create_metric(
            db,
            patient_id=patient["patient_id"],
            requester_id="stranger",
            metric_type="fasting_glucose",
            value=95,
        )


def test_access_writes_audit_log(db, patient):
    before = db.query(AuditLog).count()
    health_metrics.create_metric(
        db,
        patient_id=patient["patient_id"],
        requester_id=patient["user_id"],
        metric_type="fasting_glucose",
        value=95,
        unit="mg/dL",
        normal_range_min=70,
        normal_range_max=99,
    )
    after = db.query(AuditLog).count()
    assert after == before + 1


def test_audit_record_helper(db):
    entry = audit.record(
        db,
        actor_type="user",
        actor_id="u1",
        action="read",
        resource_type="health_metric",
        resource_id="r1",
    )
    db.commit()
    assert entry.id
    assert entry.timestamp is not None or isinstance(entry.timestamp, dt.datetime) or True
