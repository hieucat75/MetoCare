"""Credential-hygiene regression guard.

Fails if a known-compromised pilot credential, or the gitignored pilot-secrets
directory, ever reappears in tracked files. The needle is assembled from parts so
this test file is not itself a match.
"""

from __future__ import annotations

import pathlib
import subprocess

_REPO = pathlib.Path(__file__).resolve().parents[2]

# Known-compromised secrets that must never reappear in tracked files. Each is
# assembled from parts so `git grep` does not match this very file.
_COMPROMISED = [
    "Pilot" + "1234",  # rotated pilot patient password
    "AkfR8" + "hfhbE5sgRkUUFs6E61j",  # rotated dev Postgres admin password
]


def _git_grep(pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-nI", "-e", pattern],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def test_compromised_credentials_not_in_tracked_files():
    for needle in _COMPROMISED:
        hits = _git_grep(needle)
        assert hits == [], f"compromised credential present in tracked files: {hits}"


def test_pilot_secrets_dir_not_tracked():
    r = subprocess.run(
        ["git", "ls-files", "backend/.pilot-secrets"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert r.stdout.strip() == "", "pilot-secrets must never be tracked in Git"
