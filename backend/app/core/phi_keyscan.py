"""Which key is a stored PHI value actually encrypted with?

Written after the staging incident of 2026-08-06, where the Alembic migration
job ran without `MCP_ENCRYPTION_KEYS` and the SEC-F11 / j4_m10 data migrations
encrypted every Meto message, OCR candidate field, medication statement and
notification body with the development default committed to this repository.
The application then started with the real Key Vault key and could not read any
of it.

The post-deploy crypto smoke DID catch it, and then described it badly::

    {"entity":"meto_message.content","reason":"legacy_row_undecryptable","result":"fail"}
    …
    {"entities_checked":2,"failures":4,"legacy_rows_total":0}

`legacy_rows_total=0` next to four failures reads as "no legacy rows were
affected". The truth was the opposite: the counter stayed at zero *because*
every sampled row failed — the scan raised on the first bad row and never
incremented. A blast-radius number that goes DOWN as the blast radius goes up is
worse than no number, and this one sat in the incident's own evidence.

So classification is separated from counting, and every scanned row lands in
exactly one explicitly named bucket:

``plaintext_legacy_rows``
    Not ciphertext at all. The column requires encryption, so this is a row the
    migration never converted.
``ciphertext_target_key_rows``
    Reads correctly under the key the application is running with. The healthy
    state.
``ciphertext_source_key_rows``
    Reads only under the *source* key — in the incident, the repository default.
    Confidentiality is already lost for these; they also break every read.
``ciphertext_unreadable_rows``
    Fernet-shaped and readable under neither key. Corruption, or a third key
    nobody has. These are never rewritten by tooling; they need a restore.

Nesting is resolved, not guessed at. A value the migration re-encrypted on top
of existing app ciphertext is ``source(target(plaintext))``: the outer layer
needs the source key and the inner needs the target, so it is a
``ciphertext_source_key_rows`` row of depth 2. Peeling both layers is the only
way to tell it apart from corruption.

Nothing here logs, and no function returns a value that could be printed by
accident: `Resolution.plaintext` is PHI and callers are expected to use it only
to re-encrypt.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import InvalidToken, MultiFernet

from .crypto import _MAX_DECRYPT_DEPTH, is_fernet_token

CLASS_PLAINTEXT = "plaintext_legacy_rows"
CLASS_TARGET = "ciphertext_target_key_rows"
CLASS_SOURCE = "ciphertext_source_key_rows"
CLASS_UNREADABLE = "ciphertext_unreadable_rows"

#: Every bucket, in report order. Emitting all four every time — including the
#: zeros — is deliberate: an absent key reads as "not measured", and the whole
#: point of this module is that a missing number got read as a safe one.
CLASSES = (CLASS_PLAINTEXT, CLASS_TARGET, CLASS_SOURCE, CLASS_UNREADABLE)

#: Buckets that mean the deployment cannot read its own PHI.
FAILING_CLASSES = (CLASS_PLAINTEXT, CLASS_SOURCE, CLASS_UNREADABLE)


@dataclass(frozen=True)
class Resolution:
    """What a single stored value turned out to be.

    ``plaintext`` is real PHI whenever it is not None. It exists so a
    re-encryption job can rewrite the row; it must never be logged, emitted, or
    used in a comparison whose failure message prints its operands.
    """

    classification: str
    plaintext: str | None
    layers: int
    used_source: bool

    @property
    def is_healthy(self) -> bool:
        """Readable under the target key, and wrapped exactly once."""
        return self.classification == CLASS_TARGET and self.layers == 1

    @property
    def needs_rewrite(self) -> bool:
        """Recoverable, but not in the state the application needs.

        Unreadable rows are excluded on purpose: there is no plaintext to write
        back, and a job that "fixed" them would be destroying evidence.
        """
        return self.plaintext is not None and not self.is_healthy


def _try(cipher: MultiFernet | None, token: str) -> str | None:
    if cipher is None:
        return None
    try:
        return cipher.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None


def resolve(
    stored: str,
    *,
    target: MultiFernet,
    source: MultiFernet | None = None,
    max_depth: int = _MAX_DECRYPT_DEPTH,
) -> Resolution:
    """Classify one stored column value, peeling nested encryption layers.

    ``target`` is the keyset the application runs with; ``source`` is the
    suspected wrong keyset (the repository default, during the 2026-08-06
    remediation). ``source`` is tried only after ``target`` fails at a layer, so
    a healthy row never touches it and the common path stays a single decrypt.
    """
    if not is_fernet_token(stored):
        return Resolution(CLASS_PLAINTEXT, stored, layers=0, used_source=False)

    current = stored
    layers = 0
    used_source = False
    for _ in range(max_depth):
        peeled = _try(target, current)
        if peeled is None:
            peeled = _try(source, current)
            if peeled is None:
                return Resolution(CLASS_UNREADABLE, None, layers, used_source)
            used_source = True
        layers += 1
        current = peeled
        if not is_fernet_token(current):
            return Resolution(
                CLASS_SOURCE if used_source else CLASS_TARGET,
                current,
                layers,
                used_source,
            )

    # Still ciphertext after max_depth peels. Reported unreadable rather than
    # returned as a token: handing a caller a `plaintext` that is itself
    # ciphertext is how a re-encryption job cements a wrapped row forever.
    return Resolution(CLASS_UNREADABLE, None, layers, used_source)


def empty_counts() -> dict[str, int]:
    """A zeroed bucket dict. Callers report every class, always."""
    return dict.fromkeys(CLASSES, 0)


def add_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    """Immutable merge of two bucket dicts (project rule: no in-place mutation)."""
    return {name: left.get(name, 0) + right.get(name, 0) for name in CLASSES}


def counted(resolutions: list[Resolution]) -> dict[str, int]:
    """Bucket counts for a batch. Every class present, zeros included."""
    counts = empty_counts()
    for r in resolutions:
        counts = add_counts(counts, {r.classification: 1})
    return counts


@dataclass(frozen=True)
class EncryptedColumn:
    """One PHI column that stores ciphertext, discovered from the ORM."""

    table: str
    column: str
    pk: str
    kind: str
    on_decrypt_failure: str
    nullable: bool

    @property
    def entity(self) -> str:
        return f"{self.table}.{self.column}"


def encrypted_columns() -> tuple[EncryptedColumn, ...]:
    """Every `EncryptedString` / `EncryptedJSON` column, read off the metadata.

    Enumerated rather than listed. A hand-maintained list is how a column added
    next quarter silently escapes the scan — and "every other SEC-F11/j4_m10
    encrypted PHI column" is not a set anyone can keep in their head. Columns
    whose primary key is not a single sortable `id` are skipped, because keyset
    pagination has nothing to page on; none exist today and the callers assert
    that.
    """
    import app.models  # noqa: F401  — registers every mapper on the metadata

    from .crypto import EncryptedJSON, EncryptedString
    from .database import Base

    found = []
    for table in Base.metadata.sorted_tables:
        pks = [c.name for c in table.primary_key.columns]
        for column in table.columns:
            if not isinstance(column.type, EncryptedString | EncryptedJSON):
                continue
            if pks != ["id"]:
                continue
            found.append(
                EncryptedColumn(
                    table=table.name,
                    column=column.name,
                    pk="id",
                    kind=type(column.type).__name__,
                    on_decrypt_failure=getattr(column.type, "on_decrypt_failure", "none"),
                    nullable=bool(column.nullable),
                )
            )
    return tuple(sorted(found, key=lambda c: (c.table, c.column)))
