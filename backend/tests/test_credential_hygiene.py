"""Credential-hygiene regression guard.

Fails if a known-compromised pilot credential, or the gitignored pilot-secrets
directory, ever reappears in tracked files. The needle is assembled from parts so
this test file is not itself a match.
"""

from __future__ import annotations

import pathlib
import subprocess

_REPO = pathlib.Path(__file__).resolve().parents[2]

# Assembled so `git grep` does not match this very file.
_COMPROMISED = "Pilot" + "1234"


def _git_grep(pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-nI", "-e", pattern],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def test_compromised_pilot_password_not_in_tracked_files():
    hits = _git_grep(_COMPROMISED)
    assert hits == [], f"compromised credential present in tracked files: {hits}"


def test_pilot_secrets_dir_not_tracked():
    r = subprocess.run(
        ["git", "ls-files", "backend/.pilot-secrets"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert r.stdout.strip() == "", "pilot-secrets must never be tracked in Git"
