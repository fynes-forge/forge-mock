"""BigQuery integration tests (emulator)."""

from __future__ import annotations
import os
from unittest.mock import patch
import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery


@pytest.fixture(autouse=True)
def force_emulator_setup():
    """Force the BigQuery client to use the local emulator."""
    # 1. Standard Env Vars
    project_id = "forge-project"
    # Check if your docker is on 9050 or 9060
    emulator_host = "http://localhost:9060"

    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["BIGQUERY_EMULATOR_HOST"] = emulator_host

    # 2. Mock the SQLAlchemy-BigQuery helper to return an emulator-pointing client
    with patch("sqlalchemy_bigquery._helpers.create_bigquery_client") as mock_helper:
        client = bigquery.Client(
            project=project_id,
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": emulator_host},
        )
        mock_helper.return_value = client

        # Also patch the auth default to prevent the 7-minute hang
        with patch("google.auth.default", return_value=(AnonymousCredentials(), project_id)):
            yield


@pytest.mark.integration
def test_bigquery_connection(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as conn:
        # If the emulator is empty, test_connection might fail on queries.
        # We just want to see if it connects without hanging.
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
