"""Static guard — ADR-04 write-path invariant, enforced repository-wide.

Runtime tests can only prove the API path is compliant; this guard catches
bypass paths (scripts, routes, future services) by asserting that the
canonical ``Medication`` model is constructed ONLY inside the sanctioned
service module. Any new writer must go through
``app.services.medication.add_medication`` — or be explicitly added to the
allowlist below with a documented reason.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    "app/services/medication.py",  # the sanctioned statement-first write path
    "app/models/clinical.py",  # the class definition itself
}

# Matches constructor calls `Medication(` but not the class definition
# (`class Medication(`) and not other classes like MedicationAdherence.
CONSTRUCTOR = re.compile(r"(?<!class )\bMedication\(")


def test_medication_constructed_only_in_service():
    violations = []
    for base in ("app", "scripts"):
        for path in sorted((BACKEND_ROOT / base).rglob("*.py")):
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            if rel in ALLOWED:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if CONSTRUCTOR.search(line):
                    violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert not violations, (
        "Medication rows must be created via app.services.medication "
        "(statement-first, ADR-04). Direct construction found at:\n"
        + "\n".join(violations)
    )
