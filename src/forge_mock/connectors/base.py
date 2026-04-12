"""Abstract base connector and shared types for database connectivity."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl
    from forge_mock.parser.schema_models import TableSchema

logger = logging.getLogger(__name__)


class InsertMode(Enum):
    """Controls how generated rows are written to an existing table."""

    append = "append"  # Add rows without touching existing data (default)
    truncate = "truncate"  # Truncate table first, then insert
    replace = "replace"  # Drop and recreate the table, then insert


class BaseConnector(ABC):
    """Abstract interface all database connectors must implement."""

    def __init__(self, connection_url: str, batch_size: int = 1000) -> None:
        self._url = connection_url
        self._batch_size = batch_size

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the database is reachable, False otherwise."""

    @abstractmethod
    def close(self) -> None:
        """Release all connection resources."""

    def __enter__(self) -> "BaseConnector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    @abstractmethod
    def introspect(
        self,
        schema: str | None = None,
        include_tables: list[str] | None = None,
    ) -> list["TableSchema"]:
        """Return TableSchema objects representing the live database schema.

        Args:
            schema: Target schema/namespace (uses database default if None).
            include_tables: Only introspect these tables (all tables if None).
        """

    @abstractmethod
    def pull_ddl(self, schema: str | None = None) -> str:
        """Return the live schema as a CREATE TABLE DDL string."""

    # ------------------------------------------------------------------
    # Data insertion
    # ------------------------------------------------------------------

    @abstractmethod
    def insert(
        self,
        table_name: str,
        df: "pl.DataFrame",
        mode: InsertMode = InsertMode.append,
        schema: str | None = None,
    ) -> int:
        """Insert a Polars DataFrame into the named table.

        Returns the number of rows inserted.
        """

    # ------------------------------------------------------------------
    # Utility methods (CLI/Profiler support)
    # ------------------------------------------------------------------

    def _mask_url(self, url: str) -> str:
        """
        Masks credentials in a connection string for safe logging.
        Provides a generic fallback; subclasses can override with dialect-specific logic.
        """
        if "@" in url:
            try:
                # Handles 'protocol://user:pass@host'
                prefix, rest = url.split("://", 1)
                if "@" in rest:
                    auth, host = rest.rsplit("@", 1)
                    return f"{prefix}://***@{host}"
            except Exception:
                return url
        return url

    def _table_to_ddl(self, table_name: str) -> str:
        """
        Returns the DDL for a specific table.
        Defaults to calling pull_ddl with the table name as the schema context.
        """
        return self.pull_ddl(table_name)
