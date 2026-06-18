"""Observability tests: request id, metrics, no-PHI structured logging."""

from __future__ import annotations

import io
import json
import logging

from app.core.logging import ContextFilter, JsonFormatter


def test_request_id_echoed_from_header(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "corr-abc-123"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "corr-abc-123"


def test_request_id_generated_when_absent(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("X-Request-ID")  # non-empty generated id


def test_metrics_endpoint_exposes_counters(client):
    client.get("/api/v1/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
    assert "http_request_duration_seconds_bucket" in r.text


def test_access_log_is_json_with_no_phi(client):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    access_logger = logging.getLogger("mcp.access")
    access_logger.addHandler(handler)
    try:
        phi = "SecretPatientNguyenVanA-DOB-1990"
        client.post("/api/v1/ai/chat", json={"message": phi})
    finally:
        access_logger.removeHandler(handler)

    out = buf.getvalue()
    assert "http_request" in out
    # The request body / PHI must NEVER appear in logs.
    assert phi not in out

    last_line = [line for line in out.strip().splitlines() if line][-1]
    rec = json.loads(last_line)
    assert rec["event"] == "http_request"
    assert rec["path"].endswith("/ai/chat")
    assert "request_id" in rec
    # Only safe metadata fields are present.
    assert set(rec).issubset(
        {"ts", "level", "logger", "message", "request_id", "user_id",
         "method", "path", "status_code", "duration_ms", "action",
         "resource_type", "event"}
    )
