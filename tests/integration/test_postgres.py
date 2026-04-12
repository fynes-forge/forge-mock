"""PostgreSQL integration tests.

Requires: FORGE_TEST_POSTGRES=postgresql://forge:forge@localhost:5432/forge_test
Start:    docker compose -f docker/docker-compose.yml up -d postgres
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import postgres_url, run_round_trip  # noqa: F401


@pytest.mark.integration
def test_postgres_connection(postgres_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(postgres_url) as conn:
        assert conn.test_connection()


@pytest.mark.integration
def test_postgres_round_trip(postgres_url: str) -> None:
    run_round_trip(postgres_url)


@pytest.mark.integration
def test_postgres_introspect_returns_tables(postgres_url: str) -> None:
    from sqlalchemy import create_engine, text
    from forge_mock.connectors.registry import get_connector

    # Ensure at least one table exists
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS forge_probe (id SERIAL PRIMARY KEY, val TEXT)")
        )
    engine.dispose()

    with get_connector(postgres_url) as connector:
        tables = connector.introspect()
        names = [t.name for t in tables]
        assert "forge_probe" in names


@pytest.mark.integration
def test_postgres_pull_ddl(postgres_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(postgres_url) as connector:
        ddl = connector.pull_ddl()
        assert "CREATE TABLE" in ddl


@pytest.mark.integration
def test_postgres_insert_modes(postgres_url: str) -> None:
    """Verify append, truncate, and replace insert modes."""
    from sqlalchemy import create_engine, text
    import polars as pl
    from forge_mock.connectors.base import InsertMode
    from forge_mock.connectors.registry import get_connector

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS forge_insert_test (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(text("TRUNCATE TABLE forge_insert_test"))

    df = pl.DataFrame({"id": list(range(10)), "name": ["test"] * 10})

    with get_connector(postgres_url) as connector:
        # Append
        n = connector.insert("forge_insert_test", df, mode=InsertMode.append)
        assert n == 10

        # Truncate then insert
        n = connector.insert("forge_insert_test", df, mode=InsertMode.truncate)
        assert n == 10

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM forge_insert_test")).scalar()
            assert count == 10  # truncate cleared previous rows

    engine.dispose()
