# Forensics — untracked migration `j4_m8_meto_message_encryption.py`

**Subject:** `backend/alembic/versions/j4_m8_meto_message_encryption.py` — present in the
working tree, **not** in git, not in any branch, never deployed.

**Verdict:** **SUPPORTED by an approved requirement (SEC-F11, P1).** It is not stray or
speculative work. It must **not** be quarantined. It should be committed — but only as
part of completing SEC-F11 properly, and only with owner approval, because it is a
PHI data migration.

**Status:** investigation complete. File left **untouched** — not committed, not edited,
not run, not deleted.

---

## 1. Provenance

| Fact | Value |
|---|---|
| Birth (filesystem) | `2026-08-04 10:25:45` |
| Modified | `2026-08-04 10:25:45` (never edited since creation) |
| Size | 2,746 bytes |
| Owner | `pth` |
| In git? | **No** — untracked; `git log --all -- 'backend/alembic/versions/*meto*'` returns nothing |
| Deployed? | **No** — staging reports head `j4_m8_consent_versioning`, this revision's parent |

### It is one third of a coherent, timestamped change set

| File | Birth | In git? |
|---|---|---|
| `backend/tests/test_meto_message_encryption.py` | `10:24:24` | **No** (untracked) |
| `backend/app/models/meto.py` | `10:25:25` | **Yes** — committed in `dd53d54` |
| `backend/alembic/versions/j4_m8_meto_message_encryption.py` | `10:25:45` | **No** (untracked) |
| `backend/app/services/meto_chat.py` | `10:45:50` | **Yes** — committed in `dd53d54` |

Three files written inside 81 seconds implementing one requirement. **Author/process:**
the prior agent session of 2026-08-04, which was interrupted by a network drop before it
could commit. The split is an artefact of that interruption, not a decision.

### How the split reached integration-candidate state

`dd53d54` ("assessment batch 2") was my recovery commit of that interrupted work. I
staged **tracked modifications** only, so `models/meto.py` and `meto_chat.py` were
committed while the untracked migration and its test were left behind. That was my
error: the commit message says the prior-session work was "recovered", and it was
recovered only partially.

---

## 2. Intended requirement — APPROVED

`docs/launch-readiness/02-SECURITY-PRIVACY-REVIEW.md` (committed, in the candidate):

- Line 38, control 7 "PHI at rest — field encryption", 🟡 PASS-WITH-LIMITATION:
  *"**Gap:** `MetoMessage.content` and `ExtractionCandidate.fields_json` are plaintext —
  see **SEC-F11**."*
- Line 124: **SEC-F11 — Meto chat message bodies (and OCR candidate fields) are PHI
  stored unencrypted, against the platform's own standard · P1**
- Line 147: SEC-F11 is listed among the items blocking **public beta / production**.

SEC-F11 sits in an approved, numbered series (SEC-F1 … SEC-F14). This is program work,
not freelancing.

---

## 3. Consumers of `meto_messages.content`

| Consumer | Line | Use |
|---|---|---|
| `app/api/v1/routes/meto.py` | 215 | `content=m.content` — serialises history to the client |
| `app/services/meto_chat.py` | 199, 298, 587 | assistant reply, SSE stream chunk, prompt-context rebuild |
| `app/services/account.py` | 261 | GDPR erasure sets `msg.content = ""` (NOT NULL column) |

All read/write by id. **Nothing filters, indexes, joins or sorts on `content`**, so
switching the column to ciphertext breaks no query — confirmed, and consistent with the
untracked test's own claim.

---

## 4. Upgrade / downgrade behaviour

Read from source; **not executed** (per instruction).

- **No DDL.** `EncryptedString` stores base64 ciphertext in the same `TEXT` column, so
  this is a pure **data migration**.
- `upgrade()` streams rows in `_BATCH_SIZE = 500` chunks, skips `None`, and skips values
  where `try_decrypt(...)` already succeeds → **idempotent, safe to re-run**.
- `downgrade()` is a true inverse: decrypts back to plaintext, skipping anything already
  plaintext or undecryptable.
- The untracked test asserts a single Alembic head, and an `upgrade head` →
  `downgrade -1` → `upgrade head` round-trip.

**Concern flagged for the migration reviewer:** `_rows()` pages with
`LIMIT/OFFSET ORDER BY id` while `_update()` mutates the same table inside the loop.
Row width changes but ordering by `id` does not, so rows should not be skipped — but
this is exactly the pattern that silently skips rows when the sort key is mutated, and
it holds one transaction across the whole table. On a large `meto_messages` this is a
long-running write.

---

## 5. Backfill requirement

The migration **is** the backfill. There is no separate step. Volume is unknown on
production (staging is synthetic).

---

## 6. Privacy / security impact — the actual finding

**SEC-F11 is currently HALF-DELIVERED in the integration candidate, and on staging.**

The model change shipped without the migration, so:

| | Behaviour |
|---|---|
| **New** Meto messages | Encrypted at rest ✅ |
| **Pre-existing** Meto messages | Remain **plaintext PHI at rest** ❌ |

Reads do not break. `crypto.py::EncryptedString.process_result_value` ends with
*"Tolerate legacy plaintext rows (pre-encryption) by returning as-is"* — a value that is
not a Fernet token is returned unchanged. So the missing migration is a **privacy gap,
not an outage**. Severity **P1**, matching SEC-F11's own rating.

This state is worse for audit than either endpoint: the security review document says
the column is plaintext, while the code says it is encrypted, and both are half-right.

### Separate defect in the COMMITTED code

`backend/app/models/meto.py:81-82` declares:

```python
content: Mapped[str] = mapped_column(
    EncryptedString(on_decrypt_failure="none"), nullable=False
)
```

`app/core/crypto.py:126-129` states the rule for its own type:

> `"raise"` — **Required for non-nullable columns** (a silent `None` would violate the
> NOT NULL contract and can crash response serialization)

`content` is `nullable=False` and uses `"none"`. The `"none"` branch fires only for
**undecryptable ciphertext** (wrong/rotated key), not for legacy plaintext — so today it
is latent. But after a key rotation gone wrong, message bodies would silently read back
as `None` on a NOT NULL column instead of failing loudly. This contradicts the module's
documented rule and is **P1**, independent of the migration.

The model comment at line 77 asserts `on_decrypt_failure="none"` "matches" a precedent;
that justification should be re-examined against the crypto docstring rather than
accepted.

---

## 7. Alembic head impact

```
… → j3_m5_medication_schedule → j4_m8_consent_versioning        ← current head (git, staging)
                                          └→ j4_m8_meto_message_encryption   ← untracked child
```

Linear child, **not** a second head. Committing it moves the head by exactly one
revision. Revision id is 29 chars, within the Postgres `alembic_version.version_num`
VARCHAR(32) limit that caused a past deploy incident.

**Consequence of committing:** the next staging deploy would run this data migration
against the staging database automatically, since the deploy runs `alembic upgrade head`
as a one-shot job. That is why this is an owner decision, not a cleanup.

---

## 8. Disposition

**Do not quarantine.** The instruction's quarantine branch was conditional on the file
*not* being supported by an approved requirement — it is supported (SEC-F11, P1,
approved, production-blocking).

**Do not commit it silently either.** It is a PHI data migration whose commit changes
what the next deploy executes.

### Recommended completion of SEC-F11 (needs owner approval)

1. Commit the migration **together with** its test `backend/tests/test_meto_message_encryption.py`
   — they were written as one unit and the test is the only coverage of the round-trip.
2. Resolve the `on_decrypt_failure="none"` vs `nullable=False` contradiction first —
   either change to `"raise"` or amend the crypto docstring with an explicit, reviewed
   exception for chat history.
3. Address the LIMIT/OFFSET-while-updating pattern and transaction size before it runs
   against a populated production table.
4. Note that SEC-F11 also covers **`ExtractionCandidate.fields_json`**, which this
   migration does **not** touch. Closing SEC-F11 needs that too, or the requirement must
   be formally split.

Until then the file stays exactly where it is: untracked, unrun, unmodified.
