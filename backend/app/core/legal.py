"""Current legal document versions.

Single source of truth for Terms of Use / Privacy Policy versions the app
presents and records. Bump ``CURRENT_TERMS_VERSION`` when the Terms change to
force re-acceptance (a new ``terms_consents`` row is written per version).
"""

from __future__ import annotations

import os

CURRENT_TERMS_VERSION = "1.0"
CURRENT_PRIVACY_VERSION = "1.0"
# App build version, overridable at deploy time.
CURRENT_APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
