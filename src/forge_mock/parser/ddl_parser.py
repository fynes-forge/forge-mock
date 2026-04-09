"""SQL DDL parser using sqlglot to extract TableSchema objects."""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
import sqlglot.expressions as exp
from rich.console import Console

from forge_mock.parser.schema_models import ColumnSchema, ForeignKeySchema, TableSchema

console = Console(stderr=True)

# Dialect aliases accepted by sqlglot
SUPPORTED_DIALECTS = {"snowflake", "postgres", "bigquery", "trino", "duckdb", "mysql", "sqlite"}

# Normalised base-type → forge internal category
_TYPE_NORMALISE: dict[str, str] = {
    # Strings
    "VARCHAR": "VARCHAR",
    "CHAR": "CHAR",
    "TEXT": "TEXT",
    "STRING": "VARCHAR",
    "NVARCHAR": "VARCHAR",
    "CLOB": "TEXT",
    "BPCHAR": "CHAR",
    # Integers
    "INT": "INT",
    "INTEGER": "INT",
    "BIGINT": "BIGINT",
    "SMALLINT": "SMALLINT",
    "TINYINT": "SMALLINT",
    "INT64": "BIGINT",
    "INT32": "INT",
    # Floats / decimals
    "FLOAT": "FLOAT",
    "FLOAT4": "FLOAT",
    "FLOAT8": "DOUBLE",
    "DOUBLE": "DOUBLE",
    "REAL": "FLOAT",
    "NUMERIC": "DECIMAL",
    "DECIMAL": "DECIMAL",
    "NUMBER": "DECIMAL",
    # Boolean
    "BOOLEAN": "BOOLEAN",
    "BOOL": "BOOLEAN",
    # Date / time
    "DATE": "DATE",
    "TIME": "TIME",
    "DATETIME": "DATETIME",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP_NTZ": "TIMESTAMP",
    "TIMESTAMP_LTZ": "TIMESTAMP",
    "TIMESTAMP_TZ": "TIMESTAMP",
    "TIMESTAMPTZ": "TIMESTAMP",
    # UUID / binary / JSON
    "UUID": "UUID",
    "BYTES": "BINARY",
    "BINARY": "BINARY",
    "VARBINARY": "BINARY",
    "JSON": "JSON",
    "JSONB": "JSON",
    "VARIANT": "JSON",
    # Arrays / structs (treated as JSON strings)
    "ARRAY": "JSON",
    "STRUCT": "JSON",
    "RECORD": "JSON",
    "OBJECT": "JSON",
}


def _normalise_type(raw: str) -> tuple[str, list[int]]:
    """Extract base type and numeric parameters from a SQL type string."""
    raw = raw.strip().upper()
    match = re.match(r"^([A-Z_0-9 ]+?)(?:\(([^)]+)\))?$", raw)
    if not match:
        return "VARCHAR", []

    base = match.group(1).strip()
    params_str = match.group(2)

    # Resolve via lookup, fall back to VARCHAR for unknowns
    normalised = _TYPE_NORMALISE.get(base, "VARCHAR")

    params: list[int] = []
    if params_str:
        for part in params_str.split(","):
            try:
                params.append(int(part.strip()))
            except ValueError:
                pass

    return normalised, params


class DDLParser:
    """Parses one or more SQL DDL files and returns a list of TableSchema objects."""

    def __init__(self, dialect: str = "postgres") -> None:
        if dialect not in SUPPORTED_DIALECTS:
            raise ValueError(
                f"Unsupported dialect '{dialect}'. "
                f"Choose from: {', '.join(sorted(SUPPORTED_DIALECTS))}"
            )
        self.dialect = dialect

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, path: str) -> list[TableSchema]:
        """Parse a DDL file and return TableSchema objects."""
        with open(path, "r", encoding="utf-8") as fh:
            sql = fh.read()
        return self.parse_sql(sql)

    def parse_sql(self, sql: str) -> list[TableSchema]:
        """Parse raw SQL DDL string and return TableSchema objects."""
        try:
            statements = sqlglot.parse(
                sql, dialect=self.dialect, error_level=sqlglot.ErrorLevel.WARN
            )
        except Exception as exc:
            raise ValueError(f"Failed to parse SQL: {exc}") from exc

        tables: list[TableSchema] = []
        for stmt in statements:
            if stmt is None:
                continue
            if isinstance(stmt, exp.Create) and isinstance(stmt.this, exp.Schema):
                table = self._extract_table(stmt)
                if table is not None:
                    tables.append(table)
            elif isinstance(stmt, exp.Create) and isinstance(stmt.this, exp.Table):
                # CREATE TABLE without inline column definitions (rare)
                pass

        console.log(f"[dim]Parsed {len(tables)} table(s) from DDL[/dim]")
        return tables

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_table(self, create_stmt: exp.Create) -> Optional[TableSchema]:
        schema_node = create_stmt.this
        table_name = schema_node.this.name

        columns: list[ColumnSchema] = []
        table_pk_cols: set[str] = set()
        table_fks: dict[str, ForeignKeySchema] = {}

        # Collect table-level constraints first
        for expr in schema_node.expressions:
            if isinstance(expr, exp.PrimaryKey):
                for col_expr in expr.expressions:
                    table_pk_cols.add(col_expr.name)
            elif isinstance(expr, exp.ForeignKey):
                fk = self._extract_table_level_fk(expr)
                if fk:
                    for col_name in fk[0]:
                        table_fks[col_name] = fk[1]

        # Process column definitions
        for expr in schema_node.expressions:
            if isinstance(expr, exp.ColumnDef):
                col = self._extract_column(expr, table_pk_cols, table_fks)
                columns.append(col)

        if not columns:
            return None

        return TableSchema(name=table_name, dialect=self.dialect, columns=columns)

    def _extract_column(
        self,
        col_def: exp.ColumnDef,
        table_pks: set[str],
        table_fks: dict[str, ForeignKeySchema],
    ) -> ColumnSchema:
        col_name = col_def.name
        raw_type = col_def.args.get("kind")
        sql_type_str = str(raw_type) if raw_type else "VARCHAR"
        base_type, params = _normalise_type(sql_type_str)

        is_pk = col_name in table_pks
        nullable = True
        is_unique = False
        default: Optional[str] = None
        fk: Optional[ForeignKeySchema] = table_fks.get(col_name)

        for constraint in col_def.constraints:
            ctype = constraint.kind
            if isinstance(ctype, exp.PrimaryKeyColumnConstraint):
                is_pk = True
                nullable = False
            elif isinstance(ctype, exp.NotNullColumnConstraint):
                nullable = False
            elif isinstance(ctype, exp.UniqueColumnConstraint):
                is_unique = True
            elif isinstance(ctype, exp.DefaultColumnConstraint):
                default = str(constraint.args.get("this", ""))
            elif isinstance(ctype, exp.Reference):
                # Inline FK reference
                fk = self._extract_inline_fk(col_name, ctype)

        # Primary keys are implicitly not-null
        if is_pk:
            nullable = False

        return ColumnSchema(
            name=col_name,
            sql_type=sql_type_str,
            base_type=base_type,
            type_params=params,
            nullable=nullable,
            is_primary_key=is_pk,
            is_unique=is_unique,
            default=default,
            foreign_key=fk,
        )

    def _extract_inline_fk(self, col_name: str, ref: exp.Reference) -> Optional[ForeignKeySchema]:
        try:
            ref_table = ref.this.this.name
            ref_cols = ref.expressions
            ref_col = ref_cols[0].name if ref_cols else col_name
            return ForeignKeySchema(
                column=col_name,
                referenced_table=ref_table,
                referenced_column=ref_col,
            )
        except Exception:
            return None

    def _extract_table_level_fk(
        self, fk_expr: exp.ForeignKey
    ) -> Optional[tuple[list[str], ForeignKeySchema]]:
        try:
            local_cols = [c.name for c in fk_expr.expressions]
            ref = fk_expr.args.get("reference")
            if ref is None:
                return None
            ref_table = ref.this.this.name
            ref_cols_exprs = ref.expressions
            ref_col = ref_cols_exprs[0].name if ref_cols_exprs else local_cols[0]
            fk = ForeignKeySchema(
                column=local_cols[0],
                referenced_table=ref_table,
                referenced_column=ref_col,
            )
            return local_cols, fk
        except Exception:
            return None
