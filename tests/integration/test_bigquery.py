"""BigQuery integration tests (emulator).

Requires: FORGE_TEST_BIGQUERY=bigquery://forge-project/forge_test
Start:    docker compose -f docker/docker-compose.yml up -d bigquery
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_bigquery_credentials():
    """Mock Google Auth to allow connection to a local emulator without real keys."""
    with patch("google.auth.default") as mock_auth:
        # Create a dummy credential object
        mock_creds = MagicMock()
        mock_auth.return_value = (mock_creds, "forge-project")

        # Ensure the environment thinks we have a project set
        os.environ["GOOGLE_CLOUD_PROJECT"] = "forge-project"

        yield


@pytest.mark.integration
def test_bigquery_connection(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as conn:
        assert conn.test_connection()


@pytest.mark.integration
def test_bigquery_introspect(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as connector:
        tables = connector.introspect()
        assert isinstance(tables, list)


@pytest.mark.integration
def test_bigquery_pull_ddl(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as connector:
        ddl = connector.pull_ddl()
        assert isinstance(ddl, str)
