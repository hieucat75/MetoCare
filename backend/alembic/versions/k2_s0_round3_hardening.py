"""K2 Slice 0 Fix Round 3: deterministic generation ordering, content
immutability, and hash-format enforcement.

Authorized by PR #136 PTH directive (2026-07-28, after Codex Round 2):
closes two remaining integrity gaps before Codex Round 3.

1. Deterministic, DB-governed generation ordering. `created_at` can
   genuinely tie (Postgres: transaction-start time — every row inserted
   in the same transaction ties exactly; SQLite: second-resolution text —
   rows inserted within the same wall-clock second tie exactly), so
   `_select_and_promote_ai_generation`'s "single most recent attempt"
   selection was not actually deterministic under ties. Adds
   `knowledge_ai_generations.sequence_number`, assigned by the DATABASE
   itself (never the application), used as the query's authoritative
   ordering column instead of `created_at`:
   - PostgreSQL: a real `SEQUENCE`, assigned via a column `DEFAULT
     nextval(...)` evaluated inline as part of the INSERT statement
     itself — never ties, never races, no trigger needed.
   - SQLite: has no sequence object and a column `DEFAULT (SELECT ...)`
     subquery default is NOT supported by SQLite's grammar (verified
     directly — "may not contain sub-queries"), so a `sequence_number`
     column is instead populated by an `AFTER INSERT` trigger computing
     `MAX(sequence_number) + 1`, safe under SQLite's own serialized-
     single-writer transaction model (no two INSERTs can interleave
     against the same file). Because this happens as an UPDATE
     immediately after the physical INSERT (not as part of the INSERT
     itself), the append-only guard trigger must allow this one specific
     "NULL -> value" transition — same discipline this Slice already
     uses for `reviewed_by`.

2. Full content immutability: "Persisted medication knowledge content
   must not be hard-deleted. Retirement must occur through the lifecycle
   state machine" (PTH-directed Slice 0 policy). BEFORE DELETE triggers
   on all 5 ADR-13 knowledge tables reject every DELETE unconditionally,
   on both dialects — regardless of status, regardless of whether the
   row is referenced by any lifecycle/generation history. This closes the
   remaining orphan-on-delete gap the Round 1 polymorphic-INSERT guards
   never addressed (they only ever validated INSERT-time existence, never
   protected against a later DELETE of the target).

3. Hash-format enforcement: `knowledge_ai_generations.input_hash`/
   `output_hash` are documented (this table's own module docstring) as
   real SHA-256 hex digests, matching `medication_knowledge_import/
   versioning.py`'s actual `hashlib.sha256(...).hexdigest()` — these are
   INTEGRITY hashes, not opaque metadata, so format is now enforced:
   exactly 64 lowercase hexadecimal characters, full charset included,
   at the DB layer on BOTH dialects (Fix Round 3.1, 2026-07-29 — the
   original Round 3 CHECK only enforced `LENGTH(column) = 64` and
   `column = LOWER(column)`, which a same-length, all-lowercase,
   non-hex value — e.g. a Unicode lookalike character, or plain
   punctuation — could still satisfy). PostgreSQL uses its built-in `~`
   POSIX regex operator (`^[0-9a-f]{64}$`); SQLite has no `REGEXP`
   operator without registering a custom function, so it instead uses
   the built-in, always-case-sensitive `GLOB` operator with a pattern of
   64 concatenated `[0-9a-f]` single-character classes — anchoring
   charset, length, AND case in one native construct, no custom function
   required. `output_hash` remains nullable (a failed generation may
   have none) — the CHECK only applies when non-null. The ORM validator
   (`KnowledgeAIGeneration._validate_hash_format`) enforces the identical
   rule (reject, never normalize, uppercase) for the standard ORM write
   path; the DB-layer CHECK now closes the same gap for any raw-SQL
   bypass — no longer a narrower, documented-but-accepted gap.

No clinical content is authored by this migration. No existing row is
ever touched — `knowledge_ai_generations` remains empty and dormant
through Slice 0 (no AI provider calls exist yet), and the 5 knowledge
tables' own rows, if any exist by the time this runs, are read-only
affected (a new DELETE guard, nothing altering their data).

Downgrade: drops every guard/column/sequence added here, in reverse
order. The content-immutability DELETE triggers need no data-loss guard
(dropping a guard cannot destroy a row). The `sequence_number` column
downgrade DOES check the table is empty first, matching this Slice's
established discipline for any column whose removal could discard real
data if the table were ever populated.

Revision ID: k2_s0_round3_hardening
Revises: k2_s0_integrity_guards
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2_s0_round3_hardening"
down_revision: str | None = "k2_s0_integrity_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# Mirrors k2_s0_integrity_guards.py's own _SYSTEM_ACTOR_VALUES /
# _system_actor_check_sql — duplicated rather than cross-imported
# (migrations stay self-contained), used to close Codex Round 3 P1-6
# (content tables' `authored_by` had no DB-level guard against a forged
# `system:*` value, unlike knowledge_ai_generations.created_by /
# knowledge_lifecycle_transitions.actor_id, which k2_s0_integrity_guards
# already protects).
_SYSTEM_ACTOR_VALUES = (
    "system:medication-ingestion",
    "system:medication-normalization",
    "system:medication-ai-synthesis",
    "system:medication-migration",
    "system:medication-backfill",
)


def _system_actor_check_sql(column: str) -> str:
    values = ",".join(f"'{v}'" for v in _SYSTEM_ACTOR_VALUES)
    return f"{column} NOT LIKE 'system:%' OR {column} IN ({values})"


# Mirrors k2_s0_integrity_guards.py's own _AI_GENERATION_IMMUTABLE_COLUMNS
# (Round 1) — duplicated rather than cross-imported (migrations stay
# self-contained), used only to rebuild that revision's SQLite triggers
# below, which this migration's own Guard 5a silently destroys.
_AI_GENERATION_IMMUTABLE_COLUMNS = (
    "id",
    "knowledge_table",
    "target_row_id",
    "model_provider",
    "model_identifier",
    "model_version_snapshot",
    "prompt_template_id",
    "prompt_template_version",
    "normalization_pipeline_version",
    "input_source_ids",
    "input_hash",
    "output_hash",
    "generation_params",
    "generation_status",
    "failure_reason",
    "origin",
    "created_by",
    "created_at",
)


def _recreate_sqlite_round1_ai_generation_triggers() -> None:
    """k2_s0_integrity_guards (Round 1) created 5 SQLite triggers on
    `knowledge_ai_generations` (append-only DELETE guard, immutable-column
    guard, review_status/supersession finality guards, polymorphic-target
    guard). This migration's own Guard 5a runs `batch_alter_table` on that
    same table (`add_column`, `create_check_constraint` — SQLite has no
    single-step ALTER for either), which rebuilds the table (CREATE new ->
    copy -> DROP old -> RENAME) and silently drops every trigger attached
    to the OLD table object, no error (the exact hazard this migration's
    own module docstring already documents for its OWN new triggers —
    discovered here to ALSO destroy the PRIOR revision's triggers, not
    just this revision's). Verified directly: at head, only this
    migration's own 2 new triggers survived — all 5 of Round 1's were
    gone. Recreating them here, verbatim, after every batch operation on
    this table (both in upgrade() and downgrade(), since downgrade()'s own
    batch_alter_table for dropping `sequence_number` destroys them again
    too), restores exactly the schema state k2_s0_integrity_guards'
    upgrade() originally established."""
    immutable_when = "\n                OR ".join(
        f"NEW.{c} IS NOT OLD.{c}" for c in _AI_GENERATION_IMMUTABLE_COLUMNS
    )
    op.execute(
        """
        CREATE TRIGGER trg_knowledge_ai_generations_no_delete
        BEFORE DELETE ON knowledge_ai_generations
        BEGIN
            SELECT RAISE(ABORT, 'knowledge_ai_generations is append-only: DELETE is not permitted');
        END;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_knowledge_ai_generations_guard_immutable
        BEFORE UPDATE ON knowledge_ai_generations
        WHEN {immutable_when}
        BEGIN
            SELECT RAISE(ABORT, 'knowledge_ai_generations rows are append-only except review_status/superseded_by_generation_id');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_knowledge_ai_generations_guard_review_status_final
        BEFORE UPDATE ON knowledge_ai_generations
        WHEN NEW.review_status IS NOT OLD.review_status AND OLD.review_status <> 'pending'
        BEGIN
            SELECT RAISE(ABORT, 'review_status is already finalized and cannot be changed again');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_knowledge_ai_generations_guard_supersession_final
        BEFORE UPDATE ON knowledge_ai_generations
        WHEN NEW.superseded_by_generation_id IS NOT OLD.superseded_by_generation_id AND OLD.superseded_by_generation_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'superseded_by_generation_id is already set and cannot be changed again');
        END;
        """
    )
    generation_when = "\n                OR ".join(
        f"(NEW.knowledge_table = '{t}' AND NOT EXISTS (SELECT 1 FROM {t} WHERE id = NEW.target_row_id))"
        for t in _KNOWLEDGE_TABLES
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_knowledge_ai_generations_target_exists
        BEFORE INSERT ON knowledge_ai_generations
        FOR EACH ROW
        WHEN NEW.target_row_id IS NOT NULL AND ({generation_when})
        BEGIN
            SELECT RAISE(ABORT, 'no row exists in the declared knowledge_table for this polymorphic reference');
        END;
        """
    )


def _hash_format_check_sql(column: str, dialect: str) -> str:
    # Fix Round 3.1 (2026-07-29, PTH directive after Codex Round 3): the
    # Round 3 version of this check only enforced LENGTH()=64 and
    # column=LOWER(column) — a same-length, all-lowercase value containing
    # non-hex characters (e.g. a Unicode lookalike that LENGTH() counts as
    # one character, or plain punctuation) still satisfied it, even though
    # it is not a SHA-256 digest. The full hex-charset is now enforced at
    # THIS layer too, not only in the ORM validator
    # (KnowledgeAIGeneration._validate_hash_format) — closing the raw-SQL
    # bypass the ORM-only check could never cover. Uppercase is REJECTED,
    # not normalized, matching that same ORM validator's policy exactly.
    #
    # PostgreSQL: `~` is POSIX regex, built-in, exact-length anchored.
    # SQLite: has no REGEXP operator without registering a custom function
    # (verified — no built-in regex). `GLOB` is a SQLite built-in that is
    # ALWAYS case-sensitive (unlike `LIKE`, whose case sensitivity depends
    # on a pragma) — a pattern of exactly 64 single-character classes
    # `[0-9a-f]`, with no wildcard, anchors to the full string and enforces
    # charset + length + case in one native construct. Verified directly
    # against SQLite: `'g' * 64`, mixed-case, 63/65-length, and whitespace
    # values are all rejected; a genuine `hashlib.sha256(...).hexdigest()`
    # output is accepted.
    #
    # Codex Round 4 P1 (2026-07-29): `GLOB` alone is insufficient on SQLite.
    # SQLite's own string-matching internals stop at an embedded NUL
    # (U+0000) byte, so a value like `"a" * 64 + "\x00" + "attacker-
    # controlled garbage"` satisfies the 64-class GLOB pattern (it matches
    # up to the NUL) even though SQLite genuinely stores every byte after
    # it — reproduced directly via a real SQLAlchemy raw-SQL INSERT against
    # a migrated database: the 87-byte value above was accepted and
    # persisted verbatim (`hex()` showed all 87 bytes on disk) before this
    # fix. Ordinary `LENGTH(column)` cannot catch this either — SQLite's
    # own `LENGTH()` on a TEXT value ALSO stops at the same embedded NUL
    # and misreports 64. `LENGTH(CAST(column AS BLOB))`, however, measures
    # genuine byte length independent of any embedded NUL (a BLOB has no
    # C-string terminator semantics), so combining it with the existing
    # GLOB closes this exactly: the GLOB half still enforces charset, and
    # the BLOB-cast length half independently enforces that there is
    # truly nothing — NUL-prefixed or otherwise — beyond byte 64. This
    # affects both `input_hash` and `output_hash` identically. PostgreSQL
    # is not affected: its `text`/`varchar` cannot store an embedded NUL
    # byte at all (rejected at the client-encoding layer before it ever
    # reaches a CHECK), so the `~` regex alone was always sufficient there.
    if dialect == "postgresql":
        condition = f"{column} ~ '^[0-9a-f]{{64}}$'"
    else:
        condition = f"{column} GLOB '{'[0-9a-f]' * 64}' AND LENGTH(CAST({column} AS BLOB)) = 64"
    return f"{column} IS NULL OR ({condition})"


_APPEND_ONLY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION fn_ai_generations_append_only()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'knowledge_ai_generations is append-only: DELETE is not permitted (id=%)', OLD.id;
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.knowledge_table IS DISTINCT FROM OLD.knowledge_table
        OR NEW.target_row_id IS DISTINCT FROM OLD.target_row_id
        OR NEW.model_provider IS DISTINCT FROM OLD.model_provider
        OR NEW.model_identifier IS DISTINCT FROM OLD.model_identifier
        OR NEW.model_version_snapshot IS DISTINCT FROM OLD.model_version_snapshot
        OR NEW.prompt_template_id IS DISTINCT FROM OLD.prompt_template_id
        OR NEW.prompt_template_version IS DISTINCT FROM OLD.prompt_template_version
        OR NEW.normalization_pipeline_version IS DISTINCT FROM OLD.normalization_pipeline_version
        OR NEW.input_source_ids IS DISTINCT FROM OLD.input_source_ids
        OR NEW.input_hash IS DISTINCT FROM OLD.input_hash
        OR NEW.output_hash IS DISTINCT FROM OLD.output_hash
        OR NEW.generation_params IS DISTINCT FROM OLD.generation_params
        OR NEW.generation_status IS DISTINCT FROM OLD.generation_status
        OR NEW.failure_reason IS DISTINCT FROM OLD.failure_reason
        OR NEW.origin IS DISTINCT FROM OLD.origin
        OR NEW.created_by IS DISTINCT FROM OLD.created_by
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        {sequence_check}
    THEN
        RAISE EXCEPTION 'knowledge_ai_generations rows are append-only except review_status/superseded_by_generation_id (id=%)', OLD.id;
    END IF;
    {sequence_write_once}
    IF NEW.review_status IS DISTINCT FROM OLD.review_status AND OLD.review_status <> 'pending' THEN
        RAISE EXCEPTION 'review_status is already finalized (%) and cannot be changed again (id=%)', OLD.review_status, OLD.id;
    END IF;
    IF NEW.superseded_by_generation_id IS DISTINCT FROM OLD.superseded_by_generation_id AND OLD.superseded_by_generation_id IS NOT NULL THEN
        RAISE EXCEPTION 'superseded_by_generation_id is already set and cannot be changed again (id=%)', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- Guard 5a: sequence_number column + hash-format CHECKs -----------
    # MUST run before ANY trigger creation on knowledge_ai_generations
    # below: SQLite's batch_alter_table recreates the whole table (CREATE
    # new -> copy rows -> DROP old -> RENAME) for both `add_column` and
    # `create_check_constraint` (SQLite has no ALTER TABLE ADD COLUMN
    # ... / ADD CONSTRAINT for these in one step) — a trigger already
    # attached to the OLD table object does not carry over, silently
    # dropped, no error. Reproduced directly: the sequence-assignment
    # trigger created before this batch step returned `sequence_number =
    # NULL` for every row, because the later hash-CHECK batch operation
    # (originally Guard 8, below) had already silently destroyed it.
    # Running every batch operation for this table FIRST, before any
    # trigger, avoids that entirely (same lesson k2_s0_integrity_guards'
    # own docstring already documents for this exact hazard).
    if dialect == "postgresql":
        op.execute("CREATE SEQUENCE knowledge_ai_generations_sequence_number_seq;")
        op.execute(
            "ALTER TABLE knowledge_ai_generations "
            "ADD COLUMN sequence_number BIGINT NOT NULL "
            "DEFAULT nextval('knowledge_ai_generations_sequence_number_seq');"
        )
        op.execute(
            "ALTER SEQUENCE knowledge_ai_generations_sequence_number_seq "
            "OWNED BY knowledge_ai_generations.sequence_number;"
        )
    else:
        with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
            batch_op.add_column(sa.Column("sequence_number", sa.BigInteger(), nullable=True))

    with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_knowledge_ai_generations_input_hash_format",
            _hash_format_check_sql("input_hash", dialect),
        )
        batch_op.create_check_constraint(
            "ck_knowledge_ai_generations_output_hash_format",
            _hash_format_check_sql("output_hash", dialect),
        )

    # --- Guard 9: content authored_by cannot forge the system:* namespace -
    # (Codex Round 3 P1-6): k2_s0_integrity_guards' actor CHECKs cover
    # knowledge_ai_generations.created_by and knowledge_lifecycle_
    # transitions.actor_id, but never added an equivalent DB-level guard to
    # the 5 content tables' own `authored_by` column — the ORM's
    # `assert_no_forged_system_actor` validator (drug_knowledge_content.py)
    # was the ONLY thing stopping a forged `authored_by='system:attacker'`
    # value, and any raw SQL/Core INSERT bypasses it entirely.
    #
    # MUST run here, on SQLite, before `_recreate_sqlite_round1_ai_
    # generation_triggers()` below: `trg_knowledge_lifecycle_transitions_
    # target_exists` (created by an EARLIER migration, k2_s0_integrity_
    # guards, and never touched by this one) references all 5 content
    # tables by name in its own WHEN clause — SQLite raises "error in
    # trigger ...: no such table" mid-RENAME the moment ANY of those 5
    # tables' `batch_alter_table` briefly drops and recreates them, because
    # SQLite re-validates every trigger whose body references the renamed
    # table. Reproduced directly. Temporarily dropping that one
    # cross-table trigger for the duration of these 5 batch operations,
    # then recreating it verbatim immediately after, sidesteps this
    # entirely — and running before `trg_knowledge_ai_generations_target_
    # exists` is even recreated means there is nothing else to drop/restore
    # around this same hazard on the ai_generations side.
    if dialect == "postgresql":
        for table in _KNOWLEDGE_TABLES:
            op.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_authored_by_not_forged_system "
                f"CHECK ({_system_actor_check_sql('authored_by')});"
            )
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_target_exists;")
        for table in _KNOWLEDGE_TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_check_constraint(
                    f"ck_{table}_authored_by_not_forged_system",
                    _system_actor_check_sql("authored_by"),
                )
        _transition_when = "\n            OR ".join(
            f"(NEW.knowledge_table = '{t}' AND NOT EXISTS (SELECT 1 FROM {t} WHERE id = NEW.knowledge_row_id))"
            for t in _KNOWLEDGE_TABLES
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_knowledge_lifecycle_transitions_target_exists
            BEFORE INSERT ON knowledge_lifecycle_transitions
            FOR EACH ROW
            WHEN {_transition_when}
            BEGIN
                SELECT RAISE(ABORT, 'no row exists in the declared knowledge_table for this polymorphic reference');
            END;
            """
        )

    if dialect != "postgresql":
        _recreate_sqlite_round1_ai_generation_triggers()

    # --- Guard 5b: sequence assignment + uniqueness (triggers/index — ----
    # now safe to create, no further batch operation touches this table).
    op.execute(
        "CREATE UNIQUE INDEX ux_knowledge_ai_generations_sequence_number "
        "ON knowledge_ai_generations (sequence_number);"
    )
    # Codex Round 3 P1-4: a `DEFAULT`/`WHEN ... IS NULL` trigger only ever
    # fills in an OMITTED value — it does nothing to stop a caller (ORM,
    # raw SQL, any future code) from explicitly supplying its own
    # `sequence_number` and having it persisted verbatim, silently
    # defeating "a server/DB-governed monotonic sequence rather than a
    # random identifier" (PTH's own directive for this fix). Both branches
    # below now unconditionally OVERWRITE whatever value was supplied,
    # every single insert, so the DB is the only real source of this
    # value regardless of what the client sends.
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION fn_ai_generations_assign_sequence()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.sequence_number := nextval('knowledge_ai_generations_sequence_number_seq');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_knowledge_ai_generations_assign_sequence
            BEFORE INSERT ON knowledge_ai_generations
            FOR EACH ROW EXECUTE FUNCTION fn_ai_generations_assign_sequence();
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER trg_knowledge_ai_generations_assign_sequence
            AFTER INSERT ON knowledge_ai_generations
            FOR EACH ROW
            BEGIN
                UPDATE knowledge_ai_generations
                SET sequence_number = (
                    SELECT COALESCE(MAX(sequence_number), 0) + 1
                    FROM knowledge_ai_generations
                    WHERE id != NEW.id
                )
                WHERE id = NEW.id;
            END;
            """
        )

    # --- Guard 6: sequence_number is write-once (extends the existing ----
    # k2_s0_integrity_guards append-only trigger to cover the new column).
    if dialect == "postgresql":
        op.execute(
            _APPEND_ONLY_FUNCTION_SQL.format(
                sequence_check="",
                sequence_write_once=(
                    "IF OLD.sequence_number IS NOT NULL AND NEW.sequence_number IS DISTINCT FROM OLD.sequence_number THEN "
                    "RAISE EXCEPTION 'sequence_number is write-once once assigned and cannot be changed again (id=%)', OLD.id; END IF;"
                ),
            )
        )
    else:
        op.execute(
            """
            CREATE TRIGGER trg_knowledge_ai_generations_guard_sequence_number
            BEFORE UPDATE ON knowledge_ai_generations
            WHEN OLD.sequence_number IS NOT NULL AND NEW.sequence_number IS NOT OLD.sequence_number
            BEGIN
                SELECT RAISE(ABORT, 'sequence_number is write-once once assigned and cannot be changed again');
            END;
            """
        )

    # --- Guard 7: full content immutability — no hard delete, ever --------
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION fn_knowledge_content_no_hard_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'TRUNCATE' THEN
                    RAISE EXCEPTION 'persisted medication knowledge content must not be hard-deleted (table=%) — retire it through the lifecycle state machine instead', TG_TABLE_NAME;
                END IF;
                RAISE EXCEPTION 'persisted medication knowledge content must not be hard-deleted (table=%, id=%) — retire it through the lifecycle state machine instead', TG_TABLE_NAME, OLD.id;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table in _KNOWLEDGE_TABLES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_no_hard_delete
                BEFORE DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION fn_knowledge_content_no_hard_delete();

                CREATE TRIGGER trg_{table}_no_truncate
                BEFORE TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION fn_knowledge_content_no_hard_delete();
                """
            )
    else:
        for table in _KNOWLEDGE_TABLES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_no_hard_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, 'persisted medication knowledge content must not be hard-deleted — retire it through the lifecycle state machine instead');
                END;
                """
            )
    # Guard 8 (hash-format CHECK constraints) is applied earlier, as part
    # of Guard 5a above — see that section's docstring for why it must
    # run before any trigger on this table is created.


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Guard 5 non-emptiness check — MUST run before any other statement in
    # this function (Codex Round 3 P1-1): on SQLite, every DDL statement
    # below is independently auto-committed the instant it runs (SQLite has
    # no transactional DDL) — if the check ran later (as it originally did,
    # after Guards 8/7/6 had already dropped the hash CHECKs, content
    # DELETE triggers, and restored the pre-round-3 append-only function),
    # a refused downgrade would still leave the database durably
    # de-hardened while `alembic_version` stays stamped at this revision's
    # head, since raising here never updates that stamp. Reproduced
    # directly: upgrade to head, insert one knowledge_ai_generations row,
    # attempt this downgrade — with the check running late, sqlite_master
    # showed the Round 1 AI-generation triggers and the 5 content
    # no-hard-delete triggers already gone even though the refusal fired.
    # Checking first, before any DDL, makes a refusal genuinely a no-op.
    count = bind.execute(sa.text("SELECT COUNT(*) FROM knowledge_ai_generations")).scalar()
    if count:
        raise RuntimeError(
            f"Refusing to downgrade: knowledge_ai_generations has {count} row(s) — "
            "dropping sequence_number would silently discard real generation-"
            "ordering data. Remediate (export/archive the data first) before "
            "downgrading past this revision."
        )

    # Guard 8
    with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_knowledge_ai_generations_output_hash_format", type_="check")
        batch_op.drop_constraint("ck_knowledge_ai_generations_input_hash_format", type_="check")

    # Guard 7
    if dialect == "postgresql":
        for table in _KNOWLEDGE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table};")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_hard_delete ON {table};")
        op.execute("DROP FUNCTION IF EXISTS fn_knowledge_content_no_hard_delete();")
    else:
        for table in _KNOWLEDGE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_hard_delete;")

    # Guard 9 removal. On SQLite, `trg_knowledge_lifecycle_transitions_
    # target_exists` (untouched so far in this downgrade — Guard 8 only
    # rebuilt knowledge_ai_generations) references all 5 content tables by
    # name in its WHEN clause, same hazard as in upgrade(): dropped here
    # for the duration of these 5 batch operations, then recreated
    # immediately after, restoring exactly the state k2_s0_integrity_guards
    # (the revision this downgrade lands on) expects to find.
    if dialect == "postgresql":
        for table in _KNOWLEDGE_TABLES:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_authored_by_not_forged_system;")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_target_exists;")
        for table in _KNOWLEDGE_TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_constraint(f"ck_{table}_authored_by_not_forged_system", type_="check")
        _transition_when = "\n            OR ".join(
            f"(NEW.knowledge_table = '{t}' AND NOT EXISTS (SELECT 1 FROM {t} WHERE id = NEW.knowledge_row_id))"
            for t in _KNOWLEDGE_TABLES
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_knowledge_lifecycle_transitions_target_exists
            BEFORE INSERT ON knowledge_lifecycle_transitions
            FOR EACH ROW
            WHEN {_transition_when}
            BEGIN
                SELECT RAISE(ABORT, 'no row exists in the declared knowledge_table for this polymorphic reference');
            END;
            """
        )

    # Guard 6 (restore the pre-round-3 append_only function body on
    # Postgres; drop the SQLite-only guard trigger)
    if dialect == "postgresql":
        op.execute(
            _APPEND_ONLY_FUNCTION_SQL.format(sequence_check="", sequence_write_once="")
        )
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_guard_sequence_number;")

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_assign_sequence ON knowledge_ai_generations;")
        op.execute("DROP FUNCTION IF EXISTS fn_ai_generations_assign_sequence();")
        op.execute("DROP INDEX IF EXISTS ux_knowledge_ai_generations_sequence_number;")
        op.execute("ALTER TABLE knowledge_ai_generations DROP COLUMN sequence_number;")
        op.execute("DROP SEQUENCE IF EXISTS knowledge_ai_generations_sequence_number_seq;")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_assign_sequence;")
        op.execute("DROP INDEX IF EXISTS ux_knowledge_ai_generations_sequence_number;")
        with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
            batch_op.drop_column("sequence_number")
        # This batch_alter_table (and Guard 8's, above) each rebuild the
        # table and silently drop every trigger on it — including
        # k2_s0_integrity_guards' 5 SQLite triggers, which this revision's
        # own upgrade() had to recreate for the identical reason (see
        # _recreate_sqlite_round1_ai_generation_triggers's docstring).
        # Recreating them here restores exactly the schema state
        # k2_s0_integrity_guards' upgrade() established, which is what a
        # downgrade TO that revision must land on.
        _recreate_sqlite_round1_ai_generation_triggers()
