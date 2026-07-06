"""Password policy tests — build/test phase.

Temporary relaxed authentication policy: passwords only need to be >=6
characters. No uppercase/lowercase/digit/special-character requirements.
Register, change-password and admin doctor-creation share the same rule.
"""

from __future__ import annotations

import os


def _email(prefix: str) -> str:
    return f"{prefix}-{os.urandom(4).hex()}@example.com"


def test_register_accepts_six_char_numeric_password(client):
    r = client.post(
        "/api/v1/auth/register", json={"email": _email("pw"), "password": "123456"}
    )
    assert r.status_code == 201, r.text


def test_register_accepts_password_without_complexity(client):
    for pw in ("abc123", "doctor", "aaaaaa"):
        r = client.post("/api/v1/auth/register", json={"email": _email("pw"), "password": pw})
        assert r.status_code == 201, (pw, r.text)


def test_register_rejects_five_char_password(client):
    r = client.post("/api/v1/auth/register", json={"email": _email("pw"), "password": "12345"})
    assert r.status_code == 422


def test_change_password_accepts_six_chars_and_rejects_five(client):
    email = _email("chg")
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "123456"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    too_short = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "123456", "new_password": "12345"},
    )
    assert too_short.status_code == 422

    ok = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "123456", "new_password": "abc123"},
    )
    assert ok.status_code == 200, ok.text
