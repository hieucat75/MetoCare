#!/usr/bin/env python
"""Container entrypoint for the post-deploy PHI crypto smoke.

Exists because of an Azure CLI parsing rule, not because the smoke needed a
wrapper. `az containerapp job create --args` declares `nargs='*'`, and argparse
stops collecting values at the first token beginning with `-`. So

    --command "python" --args "-m" "scripts.crypto_smoke" "--allow-production"

parses to `args=[]` with all three tokens landing in `extras`, and the CLI exits
2 with UnrecognizedArgumentError. The job is never created and the gate never
runs — while the log shows a failed step indistinguishable from a real wrong-key
failure, which is exactly how a gate gets muted as "the usual broken step".
(Verified against az 2.87.0's own interpreter; `--args "upgrade" "head"` parses
fine, which is why the Alembic job has always worked.)

This module takes no dash-prefixed arguments, so the workflow can invoke it as
`--command "python" --args "run_crypto_smoke.py"` and every token survives.
Living at the image's WORKDIR also puts the app root on `sys.path`, which
`python scripts/crypto_smoke.py` would not.

Production is enabled by MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION=1 rather than a flag,
for the same reason. The underlying refusal is unchanged: `crypto_smoke.run`
allow-lists non-production environments, so an unset or misspelled MCP_ENV still
fails closed.

Exit codes pass through unchanged: 0 pass, 1 fail, 2 misconfiguration.
"""

from __future__ import annotations

import os
import sys

from scripts import crypto_smoke

_TRUE = frozenset({"1", "true", "yes", "on"})


def main() -> int:
    allow_production = (
        os.environ.get("MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION", "").strip().lower() in _TRUE
    )
    return crypto_smoke.run(allow_production=allow_production)


if __name__ == "__main__":
    sys.exit(main())
