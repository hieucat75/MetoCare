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
