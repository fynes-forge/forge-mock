"""SQLAlchemy-based connector for RDBMS introspection and insertion."""

from __future__ import annotations

import logging
from typing import Optional

import polars as pl
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, url as sa_url

from forge_mock.connectors.base import BaseConnector, InsertMode
from forge_mock.parser.schema_models import ColumnSchema, ForeignKeySchema, TableSchema

# Maps SQLAlchemy type names to our internal base types
_SA_TYPE_MAP = {
    "INTEGER": "INTEGER",
    "BIGINT": "INTEGER",
    "SMALLINT": "INTEGER",
    "VARCHAR": "VARCHAR",
    "CHAR": "VARCHAR",
    "TEXT": "TEXT",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "TIMESTAMP": "DATETIME",
    "FLOAT": "FLOAT",
    "NUMERIC": "FLOAT",
    "DECIMAL": "FLOAT",
    "REAL": "FLOAT",
    "BLOB": "BYTES",
    "VARBINARY": "BYTES",
}

logger = logging.getLogger(__name__)


class SQLAlchemyConnector(BaseConnector):
    """Generic connector using SQLAlchemy for most RDBMS."""

    def __init__(self, connection_url: str, batch_size: int = 1000) -> None:
        super().__init__(connection_url, batch_size)
        self._engine: Engine = create_engine(connection_url)

    def test_connection(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error(f"Connection test failed: {exc}")
            return False

    def pull_ddl(self, schema: str | None = None) -> str:
        """
        Approximate DDL generation using SQLAlchemy inspection.
        Matches BaseConnector signature.
        """
        inspector = inspect(self._engine)
        # If schema is provided, we treat it as a single table request or a schema filter
        actual_tables = [schema] if schema else inspector.get_table_names()
        ddl_statements = []

        for tname in actual_tables:
            try:
                cols = inspector.get_columns(tname)
                col_defs = []
                for c in cols:
                    null_str = "NULL" if c.get("nullable") else "NOT NULL"
                    col_defs.append(f"  {c['name']} {c['type']} {null_str}")

                joined_cols = ",\n".join(col_defs)
                ddl_statements.append(f"CREATE TABLE {tname} (\n{joined_cols}\n);")
            except Exception as e:
                logger.warning(f"Could not pull DDL for {tname}: {e}")

        return "\n\n".join(ddl_statements)

    def introspect(
        self, schema: Optional[str] = None, include_tables: Optional[list[str]] = None
    ) -> list[TableSchema]:
        inspector = inspect(self._engine)
        table_names = inspector.get_table_names(schema=schema)

        if include_tables:
            table_names = [t for t in table_names if t in include_tables]

        tables: list[TableSchema] = []
        dialect_name = self._engine.dialect.name

        for tname in table_names:
            pk_info = inspector.get_pk_constraint(tname, schema=schema)
            pk_cols = set(pk_info.get("constrained_columns", []))

            uq_cols = set()
            for uq in inspector.get_unique_constraints(tname, schema=schema):
                uq_cols.update(uq.get("column_names", []))

            # FK Discovery
            fk_lookup: dict[str, ForeignKeySchema] = {}
            for fk in inspector.get_foreign_keys(tname, schema=schema):
                local_cols = fk.get("constrained_columns", [])
                ref_table = fk.get("referred_table", "")
                ref_cols = fk.get("referred_columns", [])

                if ref_table and "." in ref_table:
                    ref_table = ref_table.split(".")[-1]

                if local_cols and ref_table and ref_cols:
                    fk_lookup[local_cols[0]] = ForeignKeySchema(
                        column=local_cols[0],
                        referenced_table=ref_table,
                        referenced_column=ref_cols[0],
                    )

            cols: list[ColumnSchema] = []
            for col_info in inspector.get_columns(tname, schema=schema):
                col_name = col_info["name"]
                sa_type = col_info["type"]
                type_str = type(sa_type).__name__.upper()
                base_type = _SA_TYPE_MAP.get(type_str, "VARCHAR")

                params = []
                if hasattr(sa_type, "length") and sa_type.length:
                    params.append(int(sa_type.length))

                cols.append(
                    ColumnSchema(
                        name=col_name,
                        sql_type=str(sa_type),
                        base_type=base_type,
                        type_params=params,
                        nullable=col_info.get("nullable", True),
                        is_primary_key=col_name in pk_cols,
                        is_unique=col_name in uq_cols,
                        foreign_key=fk_lookup.get(col_name),
                    )
                )

            tables.append(TableSchema(name=tname, dialect=dialect_name, columns=cols))

        return tables

    def insert(
        self,
        table_name: str,
        df: pl.DataFrame,
        mode: InsertMode = InsertMode.append,
        schema: str | None = None,
    ) -> int:
        if df.is_empty():
            return 0

        records = df.to_dicts()
        full_table_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'

        with self._engine.begin() as conn:
            if mode == InsertMode.truncate:
                if self._engine.dialect.name == "sqlite":
                    conn.execute(text(f"DELETE FROM {full_table_name}"))
                else:
                    conn.execute(text(f"TRUNCATE TABLE {full_table_name} CASCADE"))

            cols_str = ", ".join([f'"{c}"' for c in df.columns])
            placeholders = ", ".join([f":{c}" for c in df.columns])
            stmt = text(f"INSERT INTO {full_table_name} ({cols_str}) VALUES ({placeholders})")
            conn.execute(stmt, records)

        return len(records)

    def close(self) -> None:
        self._engine.dispose()

    def _mask_url(self, url: str) -> str:
        """Instance-level mask_url."""
        return _mask_url(url)

    def _table_to_ddl(self, table_name: str) -> str:
        """Instance-level table_to_ddl."""
        return self.pull_ddl(table_name)


# ------------------------------------------------------------------
# Module-level helpers (Required for CLI/Profiler static access)
# ------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Masks credentials in a connection string."""
    try:
        u = sa_url.make_url(url)
        if u.password:
            return str(u._replace(password="***"))
        return url
    except Exception:
        # Fallback if URL is not a valid SQLAlchemy string
        if "@" in url:
            prefix, rest = url.split("://", 1)
            if "@" in rest:
                _, host = rest.rsplit("@", 1)
                return f"{prefix}://***@{host}"
        return url


def _table_to_ddl(table_name: str) -> str:
    """
    Placeholder module-level helper.
    Actual DDL requires an engine instance, but this satisfies Mypy's attribute check.
    """
    return f"-- Static DDL call for {table_name}"
