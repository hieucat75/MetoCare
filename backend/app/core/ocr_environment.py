"""Environment separation for the cloud OCR provider (Azure Document Intelligence).

Production ran with ``AZURE_DOC_INTEL_ENDPOINT`` pointing at
``docintel-metocare-staging`` — a resource living in ``rg-metocare-staging``.
Nothing failed, because nothing checked. It stayed harmless only by accident:
the ``documents`` consent gate refused every web upload, so no image ever
reached a provider. The moment that gate could be satisfied, production PHI
would have been sent to staging-resource-group infrastructure.

Every other environment-identity signal already fails loud (``expected_host``
for the inbound Host header, the production scan-mode guard, the synthetic-only
registration lock). The one component that receives raw patient documents had
no such check. This module is that check.

Identity, not substrings
------------------------
For an Azure Cognitive Services account, the first label of the endpoint host
*is* the resource identity — it is the account's ``customSubDomainName``, which
Azure enforces as globally unique and which cannot be pointed at another
account. Comparing that label against an expected resource name is therefore an
identity check, not a naming convention.

``MCP_AZURE_DOC_INTEL_EXPECTED_RESOURCE`` carries that expected name and is the
primary check: an exact match against the resource the environment is supposed
to use. Both deploy workflows set it. The environment-marker rules below are a
defensive fallback for a deployment that forgot to, and are deliberately weaker
— they are the backstop, never the contract.

Fails closed throughout: anything unparseable, unexpected, or absent while
cloud OCR is active is a refusal to start, not a warning.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Azure Cognitive Services endpoints are always ``<resource>.<suffix>``.
DOC_INTEL_HOST_SUFFIX = ".cognitiveservices.azure.com"

#: Markers that must never appear in the resource an environment talks to.
#: Only consulted when no expected resource name is configured.
FOREIGN_MARKERS: dict[str, tuple[str, ...]] = {
    "production": ("staging", "-stg", "dev", "test", "sandbox", "uat", "demo"),
    "staging": ("prod",),
}


class OcrEnvironmentError(RuntimeError):
    """Raised when the configured OCR provider does not belong to this environment."""


def _normalize_env(env: str) -> str:
    e = (env or "").strip().lower()
    if e in ("prod", "production"):
        return "production"
    if e in ("stg", "staging"):
        return "staging"
    return e


def resource_name_from_endpoint(endpoint: str) -> str:
    """Return the Azure resource name that an endpoint URL identifies.

    Raises OcrEnvironmentError on anything that is not a well-formed Azure
    Cognitive Services HTTPS endpoint. A malformed endpoint is never treated as
    "probably fine" — an endpoint we cannot identify is one we cannot confirm is
    ours.
    """
    raw = (endpoint or "").strip()
    if not raw:
        raise OcrEnvironmentError("AZURE_DOC_INTEL_ENDPOINT is empty.")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise OcrEnvironmentError(
            f"AZURE_DOC_INTEL_ENDPOINT must be https, got scheme {parsed.scheme!r}. "
            "Patient documents are not sent over a non-TLS transport."
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise OcrEnvironmentError(f"AZURE_DOC_INTEL_ENDPOINT has no host: {raw!r}")
    if not host.endswith(DOC_INTEL_HOST_SUFFIX):
        raise OcrEnvironmentError(
            f"AZURE_DOC_INTEL_ENDPOINT host {host!r} is not an Azure Cognitive "
            f"Services endpoint (expected *{DOC_INTEL_HOST_SUFFIX})."
        )
    name = host[: -len(DOC_INTEL_HOST_SUFFIX)]
    if not name or "." in name:
        raise OcrEnvironmentError(
            f"AZURE_DOC_INTEL_ENDPOINT host {host!r} does not name a single resource."
        )
    return name


def assert_doc_intel_environment(
    *,
    env: str,
    endpoint: str | None,
    expected_resource: str | None,
    cloud_ocr_active: bool,
    allow_cross_env: bool = False,
) -> None:
    """Refuse to start when this environment would OCR through a foreign resource.

    ``cloud_ocr_active`` is the caller's judgement that Azure OCR could actually
    be invoked (provider selected AND the opt-in flag on). When it is False this
    is a no-op: an inert credential is not a data-boundary risk, and local/dev
    runs must not be forced to configure one.
    """
    if not cloud_ocr_active:
        return

    if not (endpoint or "").strip():
        raise OcrEnvironmentError(
            "Cloud OCR is enabled (MCP_OCR_CLOUD_PROVIDER=azure with the "
            "OCR_CLOUD_FALLBACK flag on) but AZURE_DOC_INTEL_ENDPOINT is not set. "
            "Refusing to start rather than run with an unverifiable OCR provider."
        )

    name = resource_name_from_endpoint(endpoint or "")
    normalized = _normalize_env(env)

    # Primary check: exact resource identity, when the environment declares one.
    expected = (expected_resource or "").strip().lower()
    if expected:
        if name != expected:
            raise OcrEnvironmentError(
                f"env={env!r} expects Document Intelligence resource "
                f"{expected!r} but AZURE_DOC_INTEL_ENDPOINT resolves to {name!r}. "
                "Patient documents would be sent to a resource this environment "
                "does not own."
            )
        return

    # Fallback: reject a resource carrying another environment's marker.
    if allow_cross_env:
        return
    for marker in FOREIGN_MARKERS.get(normalized, ()):
        if marker in name:
            raise OcrEnvironmentError(
                f"env={env!r} would OCR through resource {name!r}, which carries "
                f"the foreign-environment marker {marker!r}. Set "
                "MCP_AZURE_DOC_INTEL_EXPECTED_RESOURCE to this environment's own "
                "resource, or MCP_ALLOW_CROSS_ENV_OCR=true to accept it explicitly."
            )
