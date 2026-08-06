#!/usr/bin/env python
"""Container entrypoint for the staging PHI re-encryption job.

Same reason `run_crypto_smoke.py` exists: `az containerapp job create --args`
declares `nargs='*'`, and argparse stops collecting at the first token beginning
with `-`. So `--args "-m" "scripts.reencrypt_phi" "--mode" "apply"` parses to
`args=[]`, every token lands in `extras`, and the CLI exits 2 without creating
the job — a failure indistinguishable in the log from the job itself failing.

The mode is therefore a bare positional: `--args "run_reencrypt_phi.py" "apply"`.
Living at the image's WORKDIR also puts the app root on `sys.path`, which
`python scripts/reencrypt_phi.py` would not.

Defaults to `dry-run`. A missing argument must not start writing.

Exit codes pass through unchanged: 0 pass, 1 fail, 2 misconfiguration/refusal.
"""

from __future__ import annotations

import sys

from scripts import reencrypt_phi


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    return reencrypt_phi.run(mode)


if __name__ == "__main__":
    sys.exit(main())
