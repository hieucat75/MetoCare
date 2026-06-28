"""SSRF guard for the lab-upload URL-paste mode (OCR Lab Upload track §7).

A patient may paste a URL to a lab-result image/PDF. Fetching an arbitrary,
user-supplied URL server-side is a classic SSRF sink: an attacker could point it
at internal services, the loopback interface, link-local addresses, or the cloud
instance-metadata endpoint (169.254.169.254) to exfiltrate credentials.

This module enforces, BEFORE any network I/O:

  * scheme ∈ {http, https} only (no file://, gopher://, ftp://, data:, …)
  * a hostname is present
  * EVERY DNS-resolved A/AAAA address is a *global* public unicast address —
    private (RFC1918), loopback, link-local (incl. 169.254.169.254 IMDS),
    unique-local, multicast, reserved, and unspecified ranges are all rejected.

``fetch_url`` then performs the GET with redirects DISABLED (a 3xx to an internal
URL is rejected, closing the redirect-based bypass), a hard timeout, and a byte
cap enforced while streaming. DNS rebinding is mitigated by validating the
resolved addresses immediately before the single, non-redirected request.

No URL, query string, or response body is ever logged here (§7 privacy).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
# Explicit block for the cloud metadata endpoints (defense in depth — these are
# also caught by the link-local / private checks below).
_BLOCKED_HOSTS = {
    "169.254.169.254",  # AWS/Azure/GCP IMDS
    "metadata.google.internal",
    "metadata.goog",
}


class SSRFError(ValueError):
    """A URL failed the SSRF allow-list. The message is safe to surface (no PHI)."""


@dataclass
class FetchedResource:
    content: bytes
    content_type: str | None


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # ip.is_global is the strongest single check, but be explicit/fail-closed.
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    # IPv4-mapped IPv6 (::ffff:10.0.0.1) — unwrap and re-check.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_public(str(ip.ipv4_mapped))
    return ip.is_global


def _resolve(host: str) -> list[str]:
    """Resolve a hostname to all its A/AAAA addresses (may raise socket.gaierror)."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return list({info[4][0] for info in infos})


def validate_public_url(url: str) -> list[str]:
    """Validate *url* is a public http(s) URL. Returns the resolved IPs.

    Raises ``SSRFError`` with a user-safe message on any violation.
    """
    if not url or not url.strip():
        raise SSRFError("URL trống.")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SSRFError("Chỉ chấp nhận đường link http/https công khai.")
    host = parts.hostname
    if not host:
        raise SSRFError("Đường link không hợp lệ.")
    if host.lower() in _BLOCKED_HOSTS:
        raise SSRFError("Đường link trỏ tới địa chỉ nội bộ không được phép.")

    # A bare IP literal must itself be public.
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        try:
            candidates = _resolve(host)
        except socket.gaierror as exc:
            raise SSRFError("Không phân giải được tên miền của đường link.") from exc

    if not candidates:
        raise SSRFError("Không phân giải được tên miền của đường link.")
    for ip in candidates:
        if not _ip_is_public(ip):
            raise SSRFError("Đường link trỏ tới địa chỉ nội bộ/riêng tư không được phép.")
    return candidates


def fetch_url(url: str, *, max_bytes: int, timeout_seconds: int) -> FetchedResource:
    """SSRF-guarded GET. Validates, then streams with redirects off + a byte cap.

    Raises ``SSRFError`` on a blocked URL/redirect or an over-size body.
    """
    validate_public_url(url)
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=timeout_seconds,
            headers={"User-Agent": "MetoCare-LabUpload/1.0"},
        ) as client:
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    # A redirect could hop to an internal target — refuse rather
                    # than re-resolve/chase it.
                    raise SSRFError("Đường link chuyển hướng — vui lòng dùng link trực tiếp.")
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "").split(";")[0].strip() or None
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise SSRFError("Tệp từ đường link vượt quá dung lượng cho phép.")
                    chunks.append(chunk)
        return FetchedResource(content=b"".join(chunks), content_type=content_type)
    except httpx.HTTPError as exc:
        # Do NOT echo the URL or underlying error detail (may contain the token).
        raise SSRFError("Không tải được nội dung từ đường link.") from exc
