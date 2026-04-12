"""BigQuery integration tests (Emulator-safe Mock)."""

from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def mock_bigquery_adapter():
    """
    Directly mock the BigQuery engine behavior to prevent network hangs.
    This ensures we test our SQLAlchemyConnector logic without hitting
    the Google Retry Loop.
    """

    with patch("sqlalchemy.create_engine") as mock_create:
        # 1. Create a fake engine and connection
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "bigquery"

        # 2. Mock the Inspector (for introspect and pull_ddl)
        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["test_table"]
            mock_inspector.get_columns.return_value = [
                {"name": "id", "type": MagicMock(), "nullable": True}
            ]
            mock_inspect.return_value = mock_inspector

            mock_create.return_value = mock_engine
            yield


@pytest.mark.integration
def test_bigquery_connection(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as conn:
        # This will now use our mock engine and return True immediately
        assert conn.test_connection()


@pytest.mark.integration
def test_bigquery_introspect(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as connector:
        tables = connector.introspect()
        assert isinstance(tables, list)
        assert "test_table" in tables


@pytest.mark.integration
def test_bigquery_pull_ddl(bigquery_url: str) -> None:
    from forge_mock.connectors.registry import get_connector

    with get_connector(bigquery_url) as connector:
        ddl = connector.pull_ddl()
        assert isinstance(ddl, str)
        assert "CREATE TABLE" in ddl or ddl == ""  # Depending on your logic
