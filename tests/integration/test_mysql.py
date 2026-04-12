"""MySQL 8 integration tests.

Requires: FORGE_TEST_MYSQL=mysql+pymysql://forge:forge@localhost:3306/forge_test
Start:    docker compose -f docker/docker-compose.yml up -d mysql
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import mysql_url, run_round_trip  # noqa: F401


@pytest.mark.integration
def test_mysql_connection(mysql_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(mysql_url) as conn:
        assert conn.test_connection()


@pytest.mark.integration
def test_mysql_round_trip(mysql_url: str) -> None:
    run_round_trip(mysql_url)


@pytest.mark.integration
def test_mysql_introspect(mysql_url: str) -> None:
    from sqlalchemy import create_engine, text
    from forge_mock.connectors.registry import get_connector

    engine = create_engine(mysql_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS forge_probe_mysql "
                "(id INT PRIMARY KEY AUTO_INCREMENT, val VARCHAR(100))"
            )
        )
    engine.dispose()

    with get_connector(mysql_url) as connector:
        tables = connector.introspect()
        assert any(t.name == "forge_probe_mysql" for t in tables)


@pytest.mark.integration
def test_mysql_pull_ddl(mysql_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(mysql_url) as connector:
        ddl = connector.pull_ddl()
        assert "CREATE TABLE" in ddl
