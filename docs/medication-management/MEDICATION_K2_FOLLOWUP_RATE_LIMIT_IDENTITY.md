# Follow-up — Rate-Limit Identity for Authenticated Endpoints

**Status:** OPEN. Not fixed. Not a merge blocker for K2 Slice 1. Recorded per
PTH's explicit instruction (2026-07-23 final pre-merge round, item 4): "Do
not redesign the app-wide rate limiter inside this slice... Do not claim
this finding is fixed."

## Finding

`enforce_rate_limit(request, action)` (`app/api/deps.py`, pre-existing —
not introduced or modified by K2 Slice 1) keys its rate-limit bucket on
`request.client.host` (`_client_key`) — the caller's IP address — even on
endpoints that require authentication and therefore already have a stable
`CurrentUser.id` available at the point `enforce_rate_limit` is called.

K2 Slice 1's two new endpoints
(`GET /api/v1/patient/medications/{medication_id}/knowledge`,
`GET /api/v1/doctor/ingredients/{drug_ingredient_id}/knowledge`) call this
same pre-existing mechanism (`routes/medication_knowledge.py`), inheriting
this property — they do not introduce it, and this slice does not attempt
to fix it.

## Why this matters (and why it's not urgent enough to block K2 Slice 1)

- **IP rotation bypasses the limit.** A caller with access to multiple
  source IPs (common, low-cost) can exceed the intended per-identity
  request rate by rotating addresses — the bucket resets per IP.
- **Shared-IP callers can over-throttle each other.** Legitimate users
  behind CGNAT, a hospital/clinic network, or a corporate proxy share one
  IP-keyed bucket; unrelated traffic from one user can exhaust the budget
  for another.
- **Not urgent for this slice specifically:** both endpoints are read-only,
  return no PHI beyond what auth+role+ownership already gate, and are not
  a destructive or state-changing surface. The security review that
  surfaced this (2026-07-23) rated it P2 — real, but not exploitable in a
  way that crosses a trust boundary this feature is meant to enforce.

## What a future fix should do

A future app-wide rate-limiting redesign (not scoped to K2 Slice 1, and
not undertaken here) should key limits by **a combination of authenticated
principal identity and trusted client/network identity**, not IP address
alone — e.g. `user.id` for authenticated endpoints, falling back to IP
only for unauthenticated ones, with consideration for legitimately
shared-IP scenarios (proxies, NAT) so a single misbehaving user cannot
consume a whole population's shared budget under one identity, while a
single user also cannot bypass their own limit by rotating IPs.

This is an **app-wide** mechanism used across many existing endpoints
(`auth.py`'s login/register/mfa flows, and now K2 Slice 1's two read
routes) — redesigning it is out of scope for any single feature slice and
should be its own, separately reviewed change.

## Scope note

This document records the finding only. It does not implement, prototype,
or partially fix the rate limiter. `app/api/deps.py`'s `enforce_rate_limit`
and `_client_key` are unmodified by K2 Slice 1.
