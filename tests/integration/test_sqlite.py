"""SQLite integration tests — no Docker required.

SQLite uses a local file by default. The URL can be overridden via
FORGE_TEST_SQLITE (e.g. sqlite:///path/to/test.db).
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import run_round_trip, sqlite_url  # noqa: F401


@pytest.mark.integration
def test_sqlite_connection(sqlite_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(sqlite_url) as conn:
        assert conn.test_connection()


@pytest.mark.integration
def test_sqlite_round_trip(sqlite_url: str) -> None:
    run_round_trip(sqlite_url)


@pytest.mark.integration
def test_sqlite_introspect(sqlite_url: str) -> None:
    from sqlalchemy import create_engine, text
    from forge_mock.connectors.registry import get_connector

    engine = create_engine(sqlite_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS forge_probe_sqlite (id INTEGER PRIMARY KEY, val TEXT)")
        )
    engine.dispose()

    with get_connector(sqlite_url) as connector:
        tables = connector.introspect()
        assert any(t.name == "forge_probe_sqlite" for t in tables)


@pytest.mark.integration
def test_sqlite_pull_ddl(sqlite_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(sqlite_url) as connector:
        ddl = connector.pull_ddl()
        assert "CREATE TABLE" in ddl


@pytest.mark.integration
def test_sqlite_always_runs() -> None:
    """SQLite needs no external service — this test always runs in CI."""
    from forge_mock.connectors.registry import get_connector

    url = "sqlite://"  # in-memory
    with get_connector(url) as connector:
        assert connector.test_connection()
