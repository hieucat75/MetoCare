"""Environment separation for the cloud OCR provider.

Production shipped with `AZURE_DOC_INTEL_ENDPOINT` pointing at
`docintel-metocare-staging`, a resource in `rg-metocare-staging`. Nothing
failed, because nothing checked. It stayed harmless only because the
`documents` consent gate refused every web upload — the moment that gate could
be satisfied, production PHI would have gone to staging infrastructure.

These tests pin the guard that now refuses to start in that situation.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.ocr_environment import (
    OcrEnvironmentError,
    assert_doc_intel_environment,
    resource_name_from_endpoint,
)

PROD_ENDPOINT = "https://docintel-metocare-prod.cognitiveservices.azure.com/"
STAGING_ENDPOINT = "https://docintel-metocare-staging.cognitiveservices.azure.com/"


def _assert(**kw):
    """Call the guard with live-cloud defaults; overrides via kwargs."""
    params = {
        "env": "production",
        "endpoint": PROD_ENDPOINT,
        "expected_resource": "docintel-metocare-prod",
        "cloud_ocr_active": True,
        "allow_cross_env": False,
    }
    params.update(kw)
    return assert_doc_intel_environment(**params)


# --------------------------------------------------------------------------- #
# The five required cases
# --------------------------------------------------------------------------- #


def test_production_with_production_endpoint_passes():
    _assert()  # must not raise


def test_production_with_staging_endpoint_fails():
    """The exact production misconfiguration this guard exists to catch."""
    with pytest.raises(OcrEnvironmentError, match="docintel-metocare-staging"):
        _assert(endpoint=STAGING_ENDPOINT)


def test_staging_with_staging_endpoint_passes():
    _assert(
        env="staging",
        endpoint=STAGING_ENDPOINT,
        expected_resource="docintel-metocare-staging",
    )


def test_missing_endpoint_when_cloud_ocr_enabled_fails():
    for missing in (None, "", "   "):
        with pytest.raises(OcrEnvironmentError, match="not set"):
            _assert(endpoint=missing)


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-url",
        "docintel-metocare-prod.cognitiveservices.azure.com",  # no scheme
        "http://docintel-metocare-prod.cognitiveservices.azure.com/",  # not TLS
        "https://",  # no host
        "https://evil.example.com/",  # not a cognitive services host
        "https://.cognitiveservices.azure.com/",  # empty resource label
    ],
)
def test_malformed_endpoint_fails(bad):
    with pytest.raises(OcrEnvironmentError):
        _assert(endpoint=bad)


# --------------------------------------------------------------------------- #
# Direction, fallback and scope
# --------------------------------------------------------------------------- #


def test_staging_must_not_use_the_production_resource():
    """The boundary violation in the other direction is still a violation."""
    with pytest.raises(OcrEnvironmentError):
        _assert(env="staging", endpoint=PROD_ENDPOINT, expected_resource=None)


def test_staging_may_use_production_resource_only_when_explicitly_approved():
    _assert(
        env="staging",
        endpoint=PROD_ENDPOINT,
        expected_resource=None,
        allow_cross_env=True,
    )


def test_marker_fallback_catches_staging_endpoint_without_an_expected_resource():
    """A deployment that forgot to declare its resource is still protected."""
    with pytest.raises(OcrEnvironmentError, match="foreign-environment marker"):
        _assert(endpoint=STAGING_ENDPOINT, expected_resource=None)


def test_expected_resource_is_an_exact_identity_match_not_a_prefix():
    """`customSubDomainName` is the resource identity — near-misses are foreign."""
    with pytest.raises(OcrEnvironmentError):
        _assert(endpoint="https://docintel-metocare-prod-2.cognitiveservices.azure.com/")


def test_guard_is_inert_when_cloud_ocr_is_not_active():
    """A dormant credential is not a data-boundary risk; local dev must still boot."""
    _assert(endpoint=STAGING_ENDPOINT, cloud_ocr_active=False)
    _assert(endpoint=None, cloud_ocr_active=False)


def test_resource_name_is_taken_from_the_custom_subdomain():
    assert resource_name_from_endpoint(PROD_ENDPOINT) == "docintel-metocare-prod"
    assert resource_name_from_endpoint(STAGING_ENDPOINT) == "docintel-metocare-staging"
    # Case and trailing path must not change identity.
    assert (
        resource_name_from_endpoint(
            "https://DocIntel-MetoCare-Prod.cognitiveservices.azure.com"
        )
        == "docintel-metocare-prod"
    )


# --------------------------------------------------------------------------- #
# Wiring: the guard actually runs at startup validation
# --------------------------------------------------------------------------- #


def _settings(**kw) -> Settings:
    # Synthetic non-default secrets, matching tests/test_document_scan_guard.py, so
    # this suite isolates the OCR-environment guard from the secret/auth guards.
    base = {
        "env": "production",
        "secret_key": "x" * 48,
        "encryption_keys": "0" * 43 + "=",
        "database_url": "postgresql://u:p@h/db",
        "document_scan_mode": "hold",
        "ocr_cloud_provider": "azure",
        "mfa_enforcement_enabled": True,
        "skip_mfa_in_dev": False,
        "password_min_length": 8,
        "password_require_complexity": True,
        "qa_fixture_enabled": False,
    }
    base.update(kw)
    return Settings(**base)


def test_startup_validation_refuses_production_pointed_at_staging(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", STAGING_ENDPOINT)
    s = _settings(azure_doc_intel_expected_resource="docintel-metocare-prod")
    with pytest.raises(OcrEnvironmentError, match="docintel-metocare-staging"):
        s.validate_required_env_vars()


def test_startup_validation_accepts_production_pointed_at_production(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", PROD_ENDPOINT)
    s = _settings(azure_doc_intel_expected_resource="docintel-metocare-prod")
    s.validate_required_env_vars()  # must not raise


def test_startup_validation_ignores_endpoint_when_fallback_flag_is_off(monkeypatch):
    """Credentials injected unconditionally by deploy must not break a flag-off env."""
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "false")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", STAGING_ENDPOINT)
    _settings().validate_required_env_vars()  # must not raise
