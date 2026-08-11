"""The document pipeline fails loud in production when no malware scan is configured.

`document_scan_mode="skip"` accepts an upload and promotes the object straight to
the servable `accepted` container. The bytes are then parsed SERVER-SIDE before any
human review — Pillow + pytesseract (`services/ocr_engine.py`) and pypdf for page
counting — so a crafted file that passes the magic-byte check reaches those parsers
unscanned.

Every comparable risk factor (default secrets, relaxed auth, the QA fixture path)
already refuses to boot in production. This guard closes the same hole for uploads.

Scoped to production only: staging deliberately runs "skip" today.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings

_REAL_SECRET = "x" * 48
_REAL_ENC = "0" * 43 + "="


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite://",
        secret_key=_REAL_SECRET,
        encryption_keys=_REAL_ENC,
        # Secure auth defaults so this suite isolates the scan-mode guard.
        mfa_enforcement_enabled=True,
        skip_mfa_in_dev=False,
        password_min_length=8,
        password_require_complexity=True,
        qa_fixture_enabled=False,
        # No cloud OCR provider: the OCR data-boundary guard reads the ambient
        # AZURE_DOC_INTEL_ENDPOINT (see core/ocr_environment.py), and a developer
        # .env pointing at staging would otherwise fire it here and mask what
        # this suite asserts.
        ocr_cloud_provider="",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_refuses_to_boot_without_a_scan(env):
    with pytest.raises(RuntimeError, match="MCP_DOCUMENT_SCAN_MODE"):
        _settings(env=env, document_scan_mode="skip").validate_required_env_vars()


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_refuses_case_insensitively(env):
    with pytest.raises(RuntimeError, match="MCP_DOCUMENT_SCAN_MODE"):
        _settings(env=env, document_scan_mode="SKIP").validate_required_env_vars()


@pytest.mark.parametrize("mode", ["hold", "clamav"])
def test_production_boots_with_a_real_posture(mode):
    _settings(env="production", document_scan_mode=mode).validate_required_env_vars()


@pytest.mark.parametrize("env", ["dev", "test", "local", "staging"])
def test_non_production_envs_may_skip(env):
    """Staging runs `skip` today; making this a staging boot failure would break
    the existing deploy, so the guard is deliberately production-only."""
    _settings(env=env, document_scan_mode="skip").validate_required_env_vars()
