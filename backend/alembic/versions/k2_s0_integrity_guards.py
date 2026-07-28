"""K2 Slice 0 Fix Round 1: persistence-level integrity guards.

Authorized by PR #136 Codex Round 1 (docs/CODEX_REVIEW_PR136_MEDICATION_
SLICE0_ROUND1.md) findings #1, #2, #3, #4 (partial), #7 — every one of
which showed that a guarantee this Slice claimed ("write-once provenance",
"fail-closed lifecycle", "append-only history", "reserved system-actor
namespace", "polymorphic references resolve to a real row") was enforced
only in the ORM/service layer, never at the database itself, so a direct
ORM attribute mutation, a Core-style UPDATE, or a raw SQL statement could
silently violate every one of them. This migration closes that gap with
real triggers/constraints on both supported engines — the service layer
remains the primary, better-error-message path; the database is now the
backstop that cannot be bypassed by construction.

Fifth and last of Slice 0's migrations so far. Purely additive: no column
is added/dropped/renamed, no existing row is touched. Every guard here is
either a CHECK constraint or a BEFORE trigger — nothing here can reject a
row that any of Slice 0's own passing tests (pre-fix-round) legitimately
wrote, only rows that violate an invariant this PR always claimed to hold.

Guards added:

1. Write-once `origin`/`authored_by` + fail-closed lifecycle-transition
   matrix (`_ALLOWED_TRANSITIONS` in knowledge_repository.py) on all 5
   ADR-13 knowledge tables. A BEFORE UPDATE trigger rejects any UPDATE
   that changes `origin` or `authored_by`, or that changes `status` to a
   pair not in {draft->clinical_review, clinical_review->approved,
   clinical_review->rejected, approved->deprecated, deprecated->retired}.
2. True append-only enforcement on `knowledge_lifecycle_transitions` (ALL
   UPDATE/DELETE rejected — every column is set once at INSERT and never
   changes) and on `knowledge_ai_generations` (every column immutable
   EXCEPT `review_status`/`superseded_by_generation_id`, each of which may
   change exactly once, away from its initial value).
3. Reserved `system:` actor namespace: a CHECK constraint on
   `knowledge_ai_generations.created_by` and
   `knowledge_lifecycle_transitions.actor_id` rejects any value that
   starts with `system:` but is not one of the 5 registered
   `SystemActor` values (app/core/system_actors.py) — closes the gap for
   raw-SQL inserts that bypass the ORM `@validates` hooks added alongside
   this migration.
4. Polymorphic-reference existence: a BEFORE INSERT trigger on
   `knowledge_lifecycle_transitions`/`knowledge_ai_generations` rejects a
   non-null `knowledge_row_id`/`target_row_id` that does not resolve to a
   real row in the row's own declared `knowledge_table` — closes the exact
   gap Codex's own repro demonstrated (an ingredient id recorded against
   `knowledge_table='drug_side_effects'`).

Engine-specific mechanism: PostgreSQL uses `PL/pgSQL` trigger functions
(dynamic `EXECUTE format(...)` for the polymorphic-existence check, since
the target table name is only known at row-insert time). SQLite has no
stored functions or dynamic SQL inside triggers, so each SQLite trigger
enumerates the 5 known knowledge tables directly in its `WHEN` clause —
functionally identical, just expressed without a shared function body.

Downgrade: drops every trigger/function/constraint added here, in reverse
dependency order. Nothing here is a data migration, so downgrade never
needs a data-loss guard — dropping a guard cannot destroy a row, only
remove a check that will no longer fire.

Revision ID: k2_s0_integrity_guards
Revises: k2_s0_add_rejected_status
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "k2_s0_integrity_guards"
down_revision: str | None = "k2_s0_add_rejected_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# Must match app/core/system_actors.py's SystemActor values exactly
# (migrations cannot import app code — same convention as every other
# migration in this chain).
_SYSTEM_ACTOR_VALUES = (
    "system:medication-ingestion",
    "system:medication-normalization",
    "system:medication-ai-synthesis",
    "system:medication-migration",
    "system:medication-backfill",
)

_ALLOWED_TRANSITION_PAIRS = (
    ("draft", "clinical_review"),
    ("clinical_review", "approved"),
    ("clinical_review", "rejected"),
    ("approved", "deprecated"),
    ("deprecated", "retired"),
)

# Every knowledge_ai_generations column that must NEVER change after
# insert (i.e. every column except review_status/superseded_by_generation_id,
# and except updated_at, which TimestampMixin's own onupdate=func.now()
# deliberately changes on every UPDATE — including the one legitimate
# review_status/supersession UPDATE this migration still permits).
_AI_GENERATION_IMMUTABLE_COLUMNS = (
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


def _system_actor_check_sql(column: str) -> str:
    values = ",".join(f"'{v}'" for v in _SYSTEM_ACTOR_VALUES)
    return f"{column} NOT LIKE 'system:%' OR {column} IN ({values})"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- Guard 1: write-once origin/authored_by + fail-closed lifecycle --
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION fn_knowledge_content_guard()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.origin IS DISTINCT FROM OLD.origin THEN
                    RAISE EXCEPTION 'origin is write-once and cannot be changed after creation (table=%, id=%)', TG_TABLE_NAME, OLD.id;
                END IF;
                IF NEW.authored_by IS DISTINCT FROM OLD.authored_by THEN
                    RAISE EXCEPTION 'authored_by is write-once and cannot be changed after creation (table=%, id=%)', TG_TABLE_NAME, OLD.id;
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status THEN
                    IF (OLD.status, NEW.status) NOT IN (
                        ('draft','clinical_review'),
                        ('clinical_review','approved'),
                        ('clinical_review','rejected'),
                        ('approved','deprecated'),
                        ('deprecated','retired')
                    ) THEN
                        RAISE EXCEPTION 'illegal lifecycle transition % -> % (table=%, id=%)', OLD.status, NEW.status, TG_TABLE_NAME, OLD.id;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table in _KNOWLEDGE_TABLES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_content_guard
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION fn_knowledge_content_guard();
                """
            )
    else:
        pairs_sql = ",".join(f"'{a}->{b}'" for a, b in _ALLOWED_TRANSITION_PAIRS)
        for table in _KNOWLEDGE_TABLES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_guard_immutable_provenance
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                WHEN NEW.origin IS NOT OLD.origin OR NEW.authored_by IS NOT OLD.authored_by
                BEGIN
                    SELECT RAISE(ABORT, 'origin/authored_by is write-once and cannot be changed after creation');
                END;
                """
            )
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_guard_lifecycle_transition
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                WHEN NEW.status IS NOT OLD.status
                    AND (OLD.status || '->' || NEW.status) NOT IN ({pairs_sql})
                BEGIN
                    SELECT RAISE(ABORT, 'illegal lifecycle transition');
                END;
                """
            )

    # --- Guard 3: reserved system:* namespace on created_by/actor_id -----
    # MUST run before Guard 2a/2b/4 below: SQLite's batch_alter_table
    # recreates the whole table (CREATE new -> copy rows -> DROP old ->
    # RENAME) to add a CHECK constraint, since SQLite has no ALTER TABLE
    # ADD CONSTRAINT. A trigger already attached to the OLD table object
    # does not carry over to the new one — SQLite silently drops it, no
    # error. Running this batch operation before creating any trigger on
    # these same two tables avoids that entirely (harmless no-op ordering
    # concern on PostgreSQL, which has real ALTER TABLE ADD CONSTRAINT and
    # never drops a table to add one).
    with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_knowledge_ai_generations_created_by_system_namespace",
            _system_actor_check_sql("created_by"),
        )
    with op.batch_alter_table("knowledge_lifecycle_transitions", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_knowledge_lifecycle_transitions_actor_id_system_namespace",
            _system_actor_check_sql("actor_id"),
        )

    # --- Guard 2a: knowledge_lifecycle_transitions is fully append-only --
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION fn_lifecycle_transitions_append_only()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'knowledge_lifecycle_transitions is append-only: % is not permitted (id=%)', TG_OP, COALESCE(OLD.id, NEW.id);
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_knowledge_lifecycle_transitions_append_only
            BEFORE UPDATE OR DELETE ON knowledge_lifecycle_transitions
            FOR EACH ROW EXECUTE FUNCTION fn_lifecycle_transitions_append_only();
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER trg_knowledge_lifecycle_transitions_no_update
            BEFORE UPDATE ON knowledge_lifecycle_transitions
            BEGIN
                SELECT RAISE(ABORT, 'knowledge_lifecycle_transitions is append-only: UPDATE is not permitted');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_knowledge_lifecycle_transitions_no_delete
            BEFORE DELETE ON knowledge_lifecycle_transitions
            BEGIN
                SELECT RAISE(ABORT, 'knowledge_lifecycle_transitions is append-only: DELETE is not permitted');
            END;
            """
        )

    # --- Guard 2b: knowledge_ai_generations append-only except the two ----
    # narrow, exactly-once-mutable fields (review_status,
    # superseded_by_generation_id).
    if dialect == "postgresql":
        immutable_checks = "\n                    OR ".join(
            f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _AI_GENERATION_IMMUTABLE_COLUMNS
        )
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION fn_ai_generations_append_only()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'knowledge_ai_generations is append-only: DELETE is not permitted (id=%)', OLD.id;
                END IF;
                IF {immutable_checks}
                THEN
                    RAISE EXCEPTION 'knowledge_ai_generations rows are append-only except review_status/superseded_by_generation_id (id=%)', OLD.id;
                END IF;
                IF NEW.review_status IS DISTINCT FROM OLD.review_status AND OLD.review_status <> 'pending' THEN
                    RAISE EXCEPTION 'review_status is already finalized (%) and cannot be changed again (id=%)', OLD.review_status, OLD.id;
                END IF;
                IF NEW.superseded_by_generation_id IS DISTINCT FROM OLD.superseded_by_generation_id AND OLD.superseded_by_generation_id IS NOT NULL THEN
                    RAISE EXCEPTION 'superseded_by_generation_id is already set and cannot be changed again (id=%)', OLD.id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_knowledge_ai_generations_append_only
            BEFORE UPDATE OR DELETE ON knowledge_ai_generations
            FOR EACH ROW EXECUTE FUNCTION fn_ai_generations_append_only();
            """
        )
    else:
        immutable_when = "\n                    OR ".join(
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

    # --- Guard 4: polymorphic reference must resolve to a real row -------
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION fn_assert_polymorphic_target_exists()
            RETURNS TRIGGER AS $$
            DECLARE
                v_row_id TEXT;
                v_exists BOOLEAN;
            BEGIN
                IF TG_TABLE_NAME = 'knowledge_ai_generations' THEN
                    v_row_id := NEW.target_row_id;
                ELSE
                    v_row_id := NEW.knowledge_row_id;
                END IF;
                IF v_row_id IS NULL THEN
                    RETURN NEW;
                END IF;
                IF NEW.knowledge_table NOT IN ('drug_usage','drug_patient_education','drug_side_effects','drug_monitoring','drug_contraindications') THEN
                    RAISE EXCEPTION 'unrecognized knowledge_table % for polymorphic reference', NEW.knowledge_table;
                END IF;
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', NEW.knowledge_table) INTO v_exists USING v_row_id;
                IF NOT v_exists THEN
                    RAISE EXCEPTION 'no row with id=% exists in % — refusing polymorphic reference (table=%)', v_row_id, NEW.knowledge_table, TG_TABLE_NAME;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_knowledge_lifecycle_transitions_target_exists
            BEFORE INSERT ON knowledge_lifecycle_transitions
            FOR EACH ROW EXECUTE FUNCTION fn_assert_polymorphic_target_exists();

            CREATE TRIGGER trg_knowledge_ai_generations_target_exists
            BEFORE INSERT ON knowledge_ai_generations
            FOR EACH ROW EXECUTE FUNCTION fn_assert_polymorphic_target_exists();
            """
        )
    else:
        transition_when = "\n                OR ".join(
            f"(NEW.knowledge_table = '{t}' AND NOT EXISTS (SELECT 1 FROM {t} WHERE id = NEW.knowledge_row_id))"
            for t in _KNOWLEDGE_TABLES
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_knowledge_lifecycle_transitions_target_exists
            BEFORE INSERT ON knowledge_lifecycle_transitions
            FOR EACH ROW
            WHEN {transition_when}
            BEGIN
                SELECT RAISE(ABORT, 'no row exists in the declared knowledge_table for this polymorphic reference');
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


def downgrade() -> None:
    """Drops every trigger/function/constraint added by this migration, in
    the exact reverse of `upgrade()`'s order: every trigger on
    `knowledge_ai_generations`/`knowledge_lifecycle_transitions` is dropped
    BEFORE the two CHECK constraints (Guard 3, via `batch_alter_table`) —
    same SQLite table-recreation hazard as `upgrade()`'s own ordering
    comment explains, just in reverse: dropping the CHECK constraints
    first would silently wipe any trigger still attached to those two
    tables' old table object. Dropping every trigger first means the later
    batch operation touches a table with nothing left on it to lose.

    None of this is a data migration — dropping a guard cannot destroy a
    row, only remove a check that will no longer fire — so, unlike every
    other Slice 0 migration, this downgrade needs no data-loss guard."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Guard 4 triggers (both target tables).
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_target_exists ON knowledge_ai_generations;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_target_exists ON knowledge_lifecycle_transitions;")
        op.execute("DROP FUNCTION IF EXISTS fn_assert_polymorphic_target_exists();")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_target_exists;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_target_exists;")

    # Guard 2b triggers (knowledge_ai_generations append-only).
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_append_only ON knowledge_ai_generations;")
        op.execute("DROP FUNCTION IF EXISTS fn_ai_generations_append_only();")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_guard_supersession_final;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_guard_review_status_final;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_guard_immutable;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_ai_generations_no_delete;")

    # Guard 2a triggers (knowledge_lifecycle_transitions append-only).
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_append_only ON knowledge_lifecycle_transitions;")
        op.execute("DROP FUNCTION IF EXISTS fn_lifecycle_transitions_append_only();")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_no_delete;")
        op.execute("DROP TRIGGER IF EXISTS trg_knowledge_lifecycle_transitions_no_update;")

    # Guard 3 CHECK constraints — last, now that no trigger remains on
    # either table for a SQLite batch-mode recreate to silently destroy.
    with op.batch_alter_table("knowledge_lifecycle_transitions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_knowledge_lifecycle_transitions_actor_id_system_namespace", type_="check")
    with op.batch_alter_table("knowledge_ai_generations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_knowledge_ai_generations_created_by_system_namespace", type_="check")

    # Guard 1 triggers (5 content tables — untouched by any batch
    # operation in this migration, so ordering relative to Guard 3 above
    # never mattered for these, but dropped last here purely to mirror
    # upgrade()'s own reading order).
    if dialect == "postgresql":
        for table in _KNOWLEDGE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_content_guard ON {table};")
        op.execute("DROP FUNCTION IF EXISTS fn_knowledge_content_guard();")
    else:
        for table in _KNOWLEDGE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_guard_lifecycle_transition;")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_guard_immutable_provenance;")
