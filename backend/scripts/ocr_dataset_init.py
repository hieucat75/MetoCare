"""Verify and initialize the ocr_dataset directory tree.

Usage:
    python scripts/ocr_dataset_init.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATASET_DIR = BACKEND_DIR / "ocr_dataset"

HOSPITALS = (
    "vinmec", "medlatec", "tamanh", "hongngoc",
    "bachmai", "bachmai108", "fv", "hoanmy",
    "thucuc", "vietduc", "other",
)

TIERS = ("golden", "benchmark")
HOSPITAL_SUBDIRS = ("images", "expected", "azure_cache", "notes")
TOP_LEVEL_DIRS = ("incoming", "anonymized", "reports", "schema")

REQUIRED_GITIGNORE_PATTERNS = (
    "images/*",
    "azure_cache/*",
    "incoming/*",
    "anonymized/*",
)


def _ensure_dir(path: Path) -> bool:
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    (path / ".gitkeep").touch()
    return True


def _check_gitignore(dataset_dir: Path) -> list[str]:
    gitignore = dataset_dir / ".gitignore"
    if not gitignore.exists():
        return list(REQUIRED_GITIGNORE_PATTERNS)
    content = gitignore.read_text()
    return [p for p in REQUIRED_GITIGNORE_PATTERNS if p not in content]


def _count_expected_files(dataset_dir: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for tier in TIERS:
        counts[tier] = {}
        for hospital in HOSPITALS:
            expected_dir = dataset_dir / tier / hospital / "expected"
            if expected_dir.exists():
                n = len(list(expected_dir.glob("*.expected.json")))
                counts[tier][hospital] = n
    return counts


def main() -> int:
    print(f"OCR Dataset: {DATASET_DIR}")
    print()

    created: list[Path] = []
    ok: list[Path] = []

    for d in TOP_LEVEL_DIRS:
        path = DATASET_DIR / d
        if _ensure_dir(path):
            created.append(path)
        else:
            ok.append(path)

    for tier in TIERS:
        for hospital in HOSPITALS:
            for subdir in HOSPITAL_SUBDIRS:
                path = DATASET_DIR / tier / hospital / subdir
                if _ensure_dir(path):
                    created.append(path)
                else:
                    ok.append(path)

    if created:
        print(f"Created {len(created)} missing directories:")
        for p in created:
            print(f"  + {p.relative_to(BACKEND_DIR)}")
        print()

    missing_patterns = _check_gitignore(DATASET_DIR)
    if missing_patterns:
        print("WARNING: .gitignore is missing PHI-protection patterns:")
        for p in missing_patterns:
            print(f"  ! {p}")
        print()
    else:
        print(".gitignore: OK — PHI-protection patterns present")

    counts = _count_expected_files(DATASET_DIR)
    total = 0
    print()
    print("Expected JSON files by tier/hospital:")
    for tier in TIERS:
        tier_total = sum(counts[tier].values())
        total += tier_total
        print(f"  {tier}/  ({tier_total} total)")
        for hospital, n in counts[tier].items():
            if n > 0:
                print(f"    {hospital}: {n}")

    print()
    print(f"Total expected files: {total}")
    print(f"Directories verified/created: {len(ok) + len(created)}")

    return 0 if not missing_patterns else 1


if __name__ == "__main__":
    sys.exit(main())
