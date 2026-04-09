"""Tests for the DDL parser module."""

from __future__ import annotations

import pytest

from forge_mock.parser.ddl_parser import DDLParser, _normalise_type
from forge_mock.parser.schema_models import ColumnSchema, ForeignKeySchema, TableSchema
from tests.fixtures import FK_DDL, MULTI_TYPE_DDL, SIMPLE_DDL


# ---------------------------------------------------------------------------
# _normalise_type unit tests
# ---------------------------------------------------------------------------


class TestNormaliseType:
    def test_varchar_with_length(self) -> None:
        base, params = _normalise_type("VARCHAR(255)")
        assert base == "VARCHAR"
        assert params == [255]

    def test_decimal_with_precision_scale(self) -> None:
        base, params = _normalise_type("DECIMAL(18,4)")
        assert base == "DECIMAL"
        assert params == [18, 4]

    def test_bare_int(self) -> None:
        base, params = _normalise_type("INT")
        assert base == "INT"
        assert params == []

    def test_unknown_type_falls_back_to_varchar(self) -> None:
        base, params = _normalise_type("FOOBARTYPE")
        assert base == "VARCHAR"

    def test_alias_normalisation(self) -> None:
        # STRING → VARCHAR (Snowflake / BigQuery alias)
        base, _ = _normalise_type("STRING")
        assert base == "VARCHAR"

    def test_timestamp_ntz(self) -> None:
        base, _ = _normalise_type("TIMESTAMP_NTZ")
        assert base == "TIMESTAMP"


# ---------------------------------------------------------------------------
# DDLParser unit tests
# ---------------------------------------------------------------------------


class TestDDLParserInit:
    def test_unsupported_dialect_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported dialect"):
            DDLParser(dialect="oracle")

    def test_supported_dialects_accepted(self) -> None:
        for d in ("postgres", "snowflake", "bigquery", "trino"):
            parser = DDLParser(dialect=d)
            assert parser.dialect == d


class TestDDLParserSimple:
    def setup_method(self) -> None:
        self.parser = DDLParser(dialect="postgres")

    def test_parses_single_table(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        assert len(tables) == 1
        assert tables[0].name == "users"

    def test_correct_column_count(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        assert len(tables[0].columns) == 7

    def test_primary_key_detected(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        pks = tables[0].primary_keys
        assert "user_id" in pks

    def test_not_null_detected(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        col_map = {c.name: c for c in tables[0].columns}
        assert col_map["username"].nullable is False
        assert col_map["age"].nullable is True

    def test_table_schema_type(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        assert isinstance(tables[0], TableSchema)

    def test_columns_are_column_schema(self) -> None:
        tables = self.parser.parse_sql(SIMPLE_DDL)
        for col in tables[0].columns:
            assert isinstance(col, ColumnSchema)

    def test_empty_sql_returns_no_tables(self) -> None:
        tables = self.parser.parse_sql("")
        assert tables == []

    def test_non_create_statement_ignored(self) -> None:
        tables = self.parser.parse_sql("SELECT 1;")
        assert tables == []


class TestDDLParserForeignKeys:
    def setup_method(self) -> None:
        self.parser = DDLParser(dialect="postgres")

    def test_parses_two_tables(self) -> None:
        tables = self.parser.parse_sql(FK_DDL)
        assert len(tables) == 2

    def test_fk_column_detected(self) -> None:
        tables = self.parser.parse_sql(FK_DDL)
        table_map = {t.name: t for t in tables}
        emp_table = table_map["employees"]
        col_map = {c.name: c for c in emp_table.columns}
        fk = col_map["dept_id"].foreign_key
        assert fk is not None
        assert isinstance(fk, ForeignKeySchema)
        assert fk.referenced_table == "departments"
        assert fk.referenced_column == "dept_id"

    def test_dependencies_resolved(self) -> None:
        tables = self.parser.parse_sql(FK_DDL)
        table_map = {t.name: t for t in tables}
        assert "departments" in table_map["employees"].dependencies

    def test_departments_has_no_deps(self) -> None:
        tables = self.parser.parse_sql(FK_DDL)
        table_map = {t.name: t for t in tables}
        assert table_map["departments"].dependencies == []


class TestDDLParserMultiType:
    def setup_method(self) -> None:
        self.parser = DDLParser(dialect="postgres")

    def test_uuid_type(self) -> None:
        tables = self.parser.parse_sql(MULTI_TYPE_DDL)
        col_map = {c.name: c for c in tables[0].columns}
        assert col_map["event_id"].base_type == "UUID"

    def test_json_type(self) -> None:
        tables = self.parser.parse_sql(MULTI_TYPE_DDL)
        col_map = {c.name: c for c in tables[0].columns}
        assert col_map["payload"].base_type == "JSON"

    def test_date_type(self) -> None:
        tables = self.parser.parse_sql(MULTI_TYPE_DDL)
        col_map = {c.name: c for c in tables[0].columns}
        assert col_map["event_date"].base_type == "DATE"


class TestDDLParserDialects:
    """Smoke-test dialect parsing."""

    SNOWFLAKE_DDL = """
    CREATE OR REPLACE TABLE orders (
        order_id  NUMBER(38,0) NOT NULL,
        amount    FLOAT        NOT NULL,
        status    VARCHAR(20),
        PRIMARY KEY (order_id)
    );
    """

    def test_snowflake_dialect(self) -> None:
        parser = DDLParser(dialect="snowflake")
        tables = parser.parse_sql(self.SNOWFLAKE_DDL)
        assert len(tables) == 1
        assert tables[0].name == "orders"
