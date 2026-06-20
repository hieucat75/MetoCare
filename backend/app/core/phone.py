"""Vietnamese mobile phone normalization + validation (patient auth).

Patients register/login with a VN mobile number instead of email. Numbers are
normalized to canonical E.164 (`+84xxxxxxxxx`) before storage/lookup so the same
human number always maps to one row regardless of input format
(`0xxxxxxxxx`, `84xxxxxxxxx`, `+84 xxx xxx xxx`).
"""

from __future__ import annotations

import re

# National significant number = 9 digits: a 2-digit mobile network prefix + 7.
# Prefixes (post 2018 plan): Viettel 32-39, Vinaphone 81-85/88/91/94,
# Mobifone 70/76-79/89/90/93, Vietnamobile 52/56/58/92, Gmobile 59/99, iTel 87, Reddi 55.
# Kept permissive within the canonical mobile ranges below.
_NATIONAL_RE = re.compile(r"^(3[2-9]|5[2-9]|7[0689]|8[1-9]|9[0-9])\d{7}$")


def normalize_vn_phone(raw: str | None) -> str | None:
    """Return the canonical ``+84xxxxxxxxx`` form, or ``None`` if not a valid
    VN mobile number.

    Accepts ``0xxxxxxxxx``, ``84xxxxxxxxx``, ``+84xxxxxxxxx`` with optional
    spaces / dashes / dots as separators.
    """
    if not raw:
        return None
    s = re.sub(r"[\s\-.()]", "", raw.strip())

    national: str | None = None
    if s.startswith("+84"):
        national = s[3:]
    elif s.startswith("84") and len(s) == 11:
        national = s[2:]
    elif s.startswith("0") and len(s) == 10:
        national = s[1:]
    elif len(s) == 9:
        national = s

    if national is None or not national.isdigit() or not _NATIONAL_RE.match(national):
        return None
    return "+84" + national


def is_valid_vn_phone(raw: str | None) -> bool:
    return normalize_vn_phone(raw) is not None
