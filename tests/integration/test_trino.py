"""Trino integration tests.

Requires: FORGE_TEST_TRINO=trino://forge@localhost:8080/memory
Start:    docker compose -f docker/docker-compose.yml up -d trino
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_trino_connection(trino_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(trino_url) as conn:
        assert conn.test_connection()


@pytest.mark.integration
def test_trino_introspect(trino_url: str) -> None:
    """Trino memory connector: create a schema + table then introspect."""
    from sqlalchemy import create_engine, text
    from forge_mock.connectors.registry import get_connector

    engine = create_engine(trino_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS memory.forge_test"))
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS memory.forge_test.probe (id INTEGER, val VARCHAR)")
        )
    engine.dispose()

    with get_connector(trino_url) as connector:
        tables = connector.introspect(schema="forge_test")
        assert any(t.name == "probe" for t in tables)


@pytest.mark.integration
def test_trino_pull_ddl(trino_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(trino_url) as connector:
        ddl = connector.pull_ddl(schema="forge_test")
        assert isinstance(ddl, str)
