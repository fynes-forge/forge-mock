"""
Integration test configuration.

Tests in this directory require live database containers. They are skipped
automatically when the relevant environment variable is not set.

Start all engines:
    docker compose -f docker/docker-compose.yml up -d

Environment variables:
    FORGE_TEST_POSTGRES   postgresql://forge:forge@localhost:5432/forge_test
    FORGE_TEST_MYSQL      mysql+pymysql://forge:forge@localhost:3306/forge_test
    FORGE_TEST_SQLITE     sqlite:///./forge_test.db  (no Docker needed)
    FORGE_TEST_TRINO      trino://forge@localhost:8080/memory
    FORGE_TEST_BIGQUERY   bigquery://forge-project/forge_test
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# DDL fixtures shared across all engine tests
# ---------------------------------------------------------------------------

FIXTURE_DDL = """
CREATE TABLE forge_departments (
    dept_id   INTEGER     NOT NULL,
    dept_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (dept_id)
);

CREATE TABLE forge_employees (
    emp_id    BIGINT       NOT NULL,
    dept_id   INTEGER      NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email     VARCHAR(255),
    salary    DECIMAL(12,2),
    hired_on  DATE,
    PRIMARY KEY (emp_id)
);
"""

# ---------------------------------------------------------------------------
# Connection URL fixtures — skipped when env var is absent
# ---------------------------------------------------------------------------


def _url_fixture(env_var: str, default: str | None = None):  # type: ignore[no-untyped-def]
    """Return a pytest fixture that yields a URL or skips the test."""

    @pytest.fixture
    def _fixture() -> str:
        url = os.environ.get(env_var, default)
        if not url:
            pytest.skip(f"{env_var} not set — skipping integration test")
        return url

    return _fixture


postgres_url = _url_fixture("FORGE_TEST_POSTGRES")
mysql_url = _url_fixture("FORGE_TEST_MYSQL")
sqlite_url = _url_fixture("FORGE_TEST_SQLITE", "sqlite:///./forge_integration_test.db")
trino_url = _url_fixture("FORGE_TEST_TRINO")
bigquery_url = _url_fixture("FORGE_TEST_BIGQUERY")


# ---------------------------------------------------------------------------
# Shared round-trip helper
# ---------------------------------------------------------------------------


def run_round_trip(connection_url: str, n_rows: int = 50) -> None:
    """
    Full integration round-trip:
      1. Connect
      2. Apply fixture DDL
      3. Introspect
      4. Generate n_rows per table
      5. Insert (truncate mode so tests are idempotent)
      6. Assert row counts via SELECT COUNT(*)
      7. Assert FK integrity
    """
    from sqlalchemy import create_engine, text

    from forge_mock.connectors.registry import get_connector
    from forge_mock.engine.forge_engine import ForgeEngine

    # Apply fixture DDL directly via SQLAlchemy
    engine = create_engine(connection_url)
    with engine.begin() as conn:
        for stmt in FIXTURE_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    pass  # Table may already exist

    # Connect, introspect, generate, insert
    with get_connector(connection_url) as connector:
        assert connector.test_connection(), "Connection failed"

        tables = connector.introspect(include_tables=["forge_departments", "forge_employees"])
        assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"

        from forge_mock.connectors.base import InsertMode

        forge = ForgeEngine(
            tables=tables,
            rows=n_rows,
            seed=42,
            output_dir="/tmp/forge-integration-staging",
            output_format="parquet",
        )
        results = forge.run()

        for tname, df in results.items():
            inserted = connector.insert(tname, df, mode=InsertMode.truncate)
            assert inserted == n_rows, f"{tname}: expected {n_rows} rows, inserted {inserted}"

    # Verify via direct SQL
    with engine.connect() as conn:
        for tname in ("forge_departments", "forge_employees"):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar()
            assert count == n_rows, f"{tname}: expected {n_rows} rows in DB, found {count}"

        # FK integrity: all employee dept_ids should exist in departments
        orphans = conn.execute(
            text(
                "SELECT COUNT(*) FROM forge_employees e "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM forge_departments d WHERE d.dept_id = e.dept_id"
                ")"
            )
        ).scalar()
        assert orphans == 0, f"FK violation: {orphans} orphaned employee rows"

    engine.dispose()
