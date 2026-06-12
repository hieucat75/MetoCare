"""Time helpers.

The app standardizes on **naive UTC** datetimes for stored timestamps so that
comparisons are consistent across backends. SQLite (dev/test) returns naive
datetimes from ``func.now()``; mixing those with tz-aware values raises
TypeError. Production PostgreSQL stores tz-aware, but normalizing to naive UTC
at the boundary keeps the foundation portable. Revisit (store tz-aware
end-to-end) when moving fully to PostgreSQL in P1.
"""

from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    """Current UTC time as a naive datetime (tzinfo stripped)."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def as_naive_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Coerce a datetime to naive UTC (drop tzinfo); pass None through."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(dt.UTC).replace(tzinfo=None)
    return value
