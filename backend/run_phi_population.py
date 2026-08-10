#!/usr/bin/env python
"""Container entrypoint for the read-only PHI population preflight.

Exists for the same Azure CLI parsing rule as `run_crypto_smoke.py`:
`az containerapp job create --args` declares `nargs='*'` and argparse stops
collecting at the first token beginning with `-`, so `--args "-m"
"scripts.phi_population"` creates no job at all. This module takes no
dash-prefixed arguments, so the workflow invokes it as
`--command "python" --args "run_phi_population.py"` and every token survives.
Living at the image's WORKDIR also puts the app root on `sys.path`.

Needs no encryption key: it counts rows, it does not decrypt them.

Exit codes pass through unchanged: 0 provably empty, 1 not empty, 2 unavailable.
"""

from __future__ import annotations

import sys

from scripts import phi_population

if __name__ == "__main__":
    sys.exit(phi_population.main())
