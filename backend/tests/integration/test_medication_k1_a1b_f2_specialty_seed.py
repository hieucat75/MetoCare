"""Integration tests for K1-A1B-F2: clinical_specialties controlled
vocabulary seed.

Runs against a REAL PostgreSQL instance — verifies the seed migration
itself (idempotency, exact code list, no reviewer identity assigned) and
that A1a's provenance.check_specialty_exists performs a genuine DB
lookup against these seeded rows (previously always returned False,
since the table was empty — see MEDICATION_PHASE_A_BLOCKING_FINDINGS.md
Finding 2).
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration

EXPECTED_CODES = {
    "clinical_pharmacy",
    "internal_medicine",
    "endocrinology",
    "cardiology",
    "nephrology",
    "gastroenterology",
    "hematology",
}


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


def _make_alembic_config(db_url: str) -> Config:
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as _conn:
        assert _conn.dialect.name == "postgresql"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "k1_a1b_f2_specialty_seed")
    yield pg_engine
    # Unwind all the way to the pre-K1 base — same rationale as F1's test
    # file: this file's module fixture must not leave the DB mid-chain
    # for sibling migration test files that assume a pristine start.
    command.downgrade(cfg, "merge_c1m08_p0med")


@pytest.fixture()
def conn(migrated_schema: sa.Engine) -> Generator[sa.Connection, None, None]:
    with migrated_schema.connect() as connection:
        trans = connection.begin()
        yield connection
        trans.rollback()


class TestSeedContent:
    def test_exactly_seven_codes_seeded(self, conn: sa.Connection) -> None:
        rows = conn.execute(sa.text("SELECT code FROM clinical_specialties")).fetchall()
        codes = {row[0] for row in rows}
        assert codes == EXPECTED_CODES

    def test_all_seeded_rows_active(self, conn: sa.Connection) -> None:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM clinical_specialties WHERE is_active = false")
        ).scalar()
        assert count == 0

    def test_no_reviewer_identity_assigned(self, conn: sa.Connection) -> None:
        """clinical_specialties has no reviewer/person column at all — this
        test documents that fact so a future PR adding one doesn't
        silently start assigning identities via this seed."""
        cols = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='clinical_specialties'"
                )
            ).fetchall()
        }
        assert cols == {"id", "code", "display_name_vi", "display_name_en", "is_active"}

    def test_display_names_populated_for_every_code(self, conn: sa.Connection) -> None:
        rows = conn.execute(
            sa.text("SELECT code, display_name_vi, display_name_en FROM clinical_specialties")
        ).fetchall()
        for code, name_vi, name_en in rows:
            assert name_vi, f"{code} missing display_name_vi"
            assert name_en, f"{code} missing display_name_en"


class TestIdempotency:
    def test_rerunning_upgrade_does_not_duplicate(self, pg_engine: sa.Engine, conn: sa.Connection) -> None:
        """Fixture already upgraded to this revision; re-invoking the
        migration module's upgrade() function directly (bound to a real
        Alembic Operations context on this test's own connection) proves
        the migration's own INSERT-if-absent logic is idempotent, not
        just that Alembic's command-line skips re-running applied
        revisions."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from alembic.script import ScriptDirectory

        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        script = ScriptDirectory.from_config(cfg)
        migration = script.get_revision("k1_a1b_f2_specialty_seed")

        before = conn.execute(sa.text("SELECT COUNT(*) FROM clinical_specialties")).scalar()
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            migration.module.upgrade()
        after = conn.execute(sa.text("SELECT COUNT(*) FROM clinical_specialties")).scalar()
        assert before == after == 7


class TestProvenanceIntegration:
    """Proves A1a's provenance.check_specialty_exists performs a real DB
    lookup against these seeded rows — previously (pre-F2) always
    returned False since the table was empty."""

    def test_check_specialty_exists_true_for_seeded_code(self, conn: sa.Connection) -> None:
        from app.services.medication_knowledge_import.provenance import check_specialty_exists

        # provenance.py takes a Session, not a raw Connection — bind one
        # to this test's transactional connection so it sees the seeded
        # (and rolled-back-after-test) data.
        from sqlalchemy.orm import Session

        session = Session(bind=conn)
        assert check_specialty_exists(session, "endocrinology") is True

    def test_check_specialty_exists_false_for_unknown_code(self, conn: sa.Connection) -> None:
        from app.services.medication_knowledge_import.provenance import check_specialty_exists
        from sqlalchemy.orm import Session

        session = Session(bind=conn)
        assert check_specialty_exists(session, "neurosurgery") is False


class TestRollback:
    def test_downgrade_removes_exactly_the_seeded_codes(self, pg_engine: sa.Engine) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, "k1_a1b_f2_specialty_seed")
        command.downgrade(cfg, "k1_a1b_f1_schema_complete")

        with pg_engine.connect() as conn:
            remaining = conn.execute(
                sa.text("SELECT code FROM clinical_specialties")
            ).fetchall()
            assert remaining == []

        command.upgrade(cfg, "head")
