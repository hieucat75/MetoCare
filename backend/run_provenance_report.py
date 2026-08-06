#!/usr/bin/env python
"""Container entrypoint for the incident provenance report.

Same reason `run_crypto_smoke.py` exists: `az containerapp job create --args`
declares `nargs='*'` and argparse stops collecting at the first token beginning
with `-`, so `--args "-m" "scripts.provenance_report"` parses to `args=[]` and
the job is never created. This module takes no arguments at all.

Read-only. Emits integers and ISO date bounds; never an identifier.
"""

from __future__ import annotations

import sys

from scripts import provenance_report


def main() -> int:
    return provenance_report.run()


if __name__ == "__main__":
    sys.exit(main())
