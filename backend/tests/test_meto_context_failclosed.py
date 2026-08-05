"""Meto must FAIL CLOSED when the patient-context build fails.

`ContextBuilder.build` supplies the medications block, the labs block AND the
`safety_flags` block (the critical-value pre-read). The old code caught every
exception and continued with an empty `AssembledContext`, so the model — which is
instructed to rely only on context — would answer "mình không thấy kết quả xét
nghiệm nào gần đây": a false assertion about the patient's record, made while a
critical value may exist, and indistinguishable from a genuine "no data".

Both the non-streaming and the streaming path must instead return an explicit,
retryable notice, and must not call the provider at all.
"""

from __future__ import annotations

import logging

import pytest
from app.services import meto_chat as chat_mod


class _LoggerCapture(logging.Handler):
    """Capture records from a NAMED logger, independent of the root handlers.

    `app.core.logging.setup_logging()` removes every root handler so the app can
    own its JSON formatting. pytest's `caplog` installs its handler on the ROOT
    logger, so any test running after app startup sees an empty caplog — which is
    a test-harness artifact, not missing logging. Attaching directly to the target
    logger makes the assertion independent of that ordering.
    """

    def __init__(self, logger_name: str):
        super().__init__(level=logging.DEBUG)
        self._logger = logging.getLogger(logger_name)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):  # noqa: D102
        self.records.append(record)

    def __enter__(self):
        self._prev_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self)
        return self

    def __exit__(self, *exc):
        self._logger.removeHandler(self)
        self._logger.setLevel(self._prev_level)
        return False

    @property
    def text(self) -> str:
        return "\n".join(r.getMessage() for r in self.records)


PHI_MESSAGE = "Đường huyết của tôi hôm nay thế nào?"


@pytest.fixture
def broken_context(monkeypatch):
    """Make the context build blow up the way a transient DB error would."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated context-build failure")

    monkeypatch.setattr(chat_mod._CONTEXT_BUILDER, "build", _boom)


def test_non_streaming_returns_the_safe_notice(client, patient, broken_context):
    res = client.post(
        "/api/v1/meto/chat",
        json={"message": PHI_MESSAGE},
        headers=patient["headers"],
    )
    assert res.status_code == 200
    body = res.json()

    assert body["content"] == chat_mod._CONTEXT_UNAVAILABLE_MSG
    # It must say the data is unavailable — NOT that there is no data.
    assert "không truy cập được" in body["content"]
    assert "Vui lòng thử lại" in body["content"]


def test_streaming_returns_the_safe_notice(client, patient, broken_context):
    res = client.post(
        "/api/v1/meto/chat/stream",
        json={"message": PHI_MESSAGE},
        headers=patient["headers"],
    )
    assert res.status_code == 200
    payload = res.text

    assert "không truy cập được" in payload
    assert "context_unavailable" in payload


def test_the_notice_never_claims_the_patient_has_no_data():
    """The distinction is the whole point: 'unavailable' must not read as 'none'."""
    msg = chat_mod._CONTEXT_UNAVAILABLE_MSG
    for forbidden in ("không thấy kết quả", "chưa có kết quả", "không có dữ liệu nào"):
        assert forbidden not in msg


def test_failure_is_logged_without_phi(client, patient, broken_context):
    with _LoggerCapture("app.services.meto_chat") as cap:
        client.post(
            "/api/v1/meto/chat",
            json={"message": PHI_MESSAGE},
            headers=patient["headers"],
        )

    assert any("context_build_failed" in r.getMessage() for r in cap.records)
    combined = cap.text
    # The patient's message, and the exception's own text, must not be logged.
    assert PHI_MESSAGE not in combined
    assert "simulated context-build failure" not in combined
    # Escalated to error — a silently-degraded answer used to be a warning.
    assert any(r.levelno >= logging.ERROR for r in cap.records)
