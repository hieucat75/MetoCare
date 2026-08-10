"""Unit tests for VN phone normalization (app/core/phone.py)."""

from __future__ import annotations

import pytest
from app.core.phone import is_valid_vn_phone, normalize_vn_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0901234567", "+84901234567"),  # local Mobifone
        ("0349999999", "+84349999999"),  # Viettel 034
        ("+84 90 123 4567", "+84901234567"),  # spaced e164
        ("8498-765-4321", "+84987654321"),  # 84 prefix + separators
        ("901234567", "+84901234567"),  # bare 9-digit national
        ("+84329999999", "+84329999999"),  # already canonical
    ],
)
def test_normalize_valid(raw, expected):
    assert normalize_vn_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "012345678",  # 01x not a mobile prefix
        "0123456789",  # 012 invalid mobile
        "090123456",  # too short (local, 9 digits)
        "09012345678",  # too long
        "+84123456789",  # 12x invalid mobile prefix
        "abcdkqj",  # junk
        "0901234abc",  # letters
        "+1 202 555 0143",  # non-VN
    ],
)
def test_normalize_invalid(raw):
    assert normalize_vn_phone(raw) is None
    assert is_valid_vn_phone(raw) is False


def test_idempotent_on_canonical():
    once = normalize_vn_phone("0987654321")
    assert once is not None
    assert normalize_vn_phone(once) == once


# ── Regression: the 090 shape reported from production on 2026-08-10 ─────────
#
# A real user's registration was rejected as "Số điện thoại di động Việt Nam
# không hợp lệ." The number was valid and the normalizer was never at fault —
# the register page reported EVERY 422 as an invalid phone, and the 422 was a
# password-policy rejection. These pin the contract the report was measured
# against, so a future regex change cannot quietly make that report true.
#
# Synthetic 090 number of the same shape. The reporter's real number is
# deliberately not committed.

_SYNTHETIC_090 = "0904641810"
_SYNTHETIC_090_E164 = "+84904641810"


@pytest.mark.parametrize(
    "raw",
    [
        "0904641810",
        "+84904641810",
        "84904641810",
        "+84 904 641 810",
        "090 464 1810",
        "090-464-1810",
    ],
)
def test_every_accepted_form_of_a_090_mobile_normalizes_to_one_e164(raw):
    assert normalize_vn_phone(raw) == _SYNTHETIC_090_E164


def test_the_090_prefix_is_inside_the_accepted_contract():
    """Mobifone 090. Named explicitly because the production report claimed
    otherwise, and a regex that dropped it would be a silent lockout."""
    assert is_valid_vn_phone(_SYNTHETIC_090)


@pytest.mark.parametrize(
    "raw",
    [
        "12345",
        "090464181",       # 8 national digits — one short
        "09046418100",     # 10 national digits — one long
        "+840904641810",   # double-prefixed: +84 followed by the trunk 0
        "+84+84904641810",
        "0104641810",      # 10 is not a mobile prefix
        "",
        None,
    ],
)
def test_invalid_numbers_still_fail(raw):
    assert normalize_vn_phone(raw) is None
