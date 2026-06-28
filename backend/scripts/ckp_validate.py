#!/usr/bin/env python3
"""MetoCare CKP QA Validator CLI.

Usage:
  python scripts/ckp_validate.py              # validate default cards dir
  python scripts/ckp_validate.py --path /custom/path
  python scripts/ckp_validate.py --verbose    # show passing cards too
"""
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from app.knowledge.qa_validator import validate_registry
from app.knowledge.registry import KnowledgeRegistry


def main():
    parser = argparse.ArgumentParser(description="Validate CKP knowledge cards")
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    reg = KnowledgeRegistry(args.path)
    cards = reg.all_cards()

    if not cards:
        print("⚠️  No cards found. Check --path or KNOWLEDGE_BASE_PATH env var.")
        sys.exit(1)

    report = validate_registry(cards)
    report.print_report()

    if args.verbose:
        passing = [
            c.knowledge_id
            for c in cards
            if not any(i.knowledge_id == c.knowledge_id for i in report.issues)
        ]
        if passing:
            print(f"\n✅ Cards with no issues: {', '.join(passing)}")

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
