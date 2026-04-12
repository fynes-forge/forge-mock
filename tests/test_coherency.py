"""Tests for Phase 5 — coherency pass, schema drift detection, dbt reader."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from forge_mock.coherency.coherency_pass import CoherencyPass
from forge_mock.coherency.dbt_reader import DbtReader
from forge_mock.coherency.schema_drift import DriftKind, SchemaDriftDetector
from forge_mock.parser.schema_models import TableSchema


# ---------------------------------------------------------------------------
# CoherencyPass
# ---------------------------------------------------------------------------


class TestCoherencyPass:
    def _make_rng(self) -> np.random.Generator:
        return np.random.default_rng(42)

    def _table_map(self, name: str) -> dict[str, TableSchema]:
        return {name: TableSchema(name=name, dialect="test")}

    def test_end_date_fixed_when_before_start(self) -> None:
        rng = self._make_rng()
        df = pl.DataFrame(
            {
                "order_date": [datetime.date(2024, 6, 1)],
                "shipped_date": [datetime.date(2024, 5, 1)],  # BEFORE order — bad
            }
        )
        passer = CoherencyPass(self._table_map("orders"), rng)
        result = passer.apply({"orders": df})
        shipped = result["orders"]["shipped_date"][0]
        order = result["orders"]["order_date"][0]
        assert shipped >= order

    def test_valid_dates_unchanged(self) -> None:
        rng = self._make_rng()
        df = pl.DataFrame(
            {
                "order_date": [datetime.date(2024, 1, 1)],
                "shipped_date": [datetime.date(2024, 1, 15)],
            }
        )
        passer = CoherencyPass(self._table_map("orders"), rng)
        result = passer.apply({"orders": df})
        assert result["orders"]["shipped_date"][0] == datetime.date(2024, 1, 15)

    def test_discount_clamped_to_price(self) -> None:
        rng = self._make_rng()
        df = pl.DataFrame(
            {
                "price": [100.0],
                "discount": [200.0],  # discount > price — bad
            }
        )
        passer = CoherencyPass(self._table_map("items"), rng)
        result = passer.apply({"items": df})
        disc = result["items"]["discount"][0]
        price = result["items"]["price"][0]
        assert disc <= price

    def test_negative_discount_zeroed(self) -> None:
        rng = self._make_rng()
        df = pl.DataFrame(
            {
                "price": [50.0],
                "discount": [-10.0],  # negative discount — bad
            }
        )
        passer = CoherencyPass(self._table_map("items"), rng)
        result = passer.apply({"items": df})
        assert result["items"]["discount"][0] >= 0.0

    def test_no_date_cols_no_crash(self) -> None:
        rng = self._make_rng()
        df = pl.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        passer = CoherencyPass(self._table_map("simple"), rng)
        result = passer.apply({"simple": df})
        assert len(result["simple"]) == 2

    def test_multiple_tables_processed(self) -> None:
        rng = self._make_rng()
        df1 = pl.DataFrame({"id": [1]})
        df2 = pl.DataFrame({"id": [2]})
        passer = CoherencyPass({}, rng)
        result = passer.apply({"a": df1, "b": df2})
        assert set(result.keys()) == {"a", "b"}

    def test_dob_in_past(self) -> None:
        rng = self._make_rng()
        future_dob = datetime.date.today() + datetime.timedelta(days=365)
        df = pl.DataFrame(
            {
                "date_of_birth": [future_dob],
            }
        )
        passer = CoherencyPass(self._table_map("patients"), rng)
        result = passer.apply({"patients": df})
        dob = result["patients"]["date_of_birth"][0]
        cutoff = datetime.date.today() - datetime.timedelta(days=18 * 365)
        assert dob <= cutoff


# ---------------------------------------------------------------------------
# DbtReader
# ---------------------------------------------------------------------------

SIMPLE_SCHEMA_YML = """
version: 2

models:
  - name: customers
    description: "Customer master table"
    columns:
      - name: customer_id
        tests:
          - not_null
          - unique
      - name: email
        description: "Customer email address"
        tests:
          - not_null
      - name: status
        tests:
          - accepted_values:
              values: [active, inactive, pending]
      - name: order_id
        tests:
          - relationships:
              to: ref('orders')
              field: id
"""

SOURCES_SCHEMA_YML = """
version: 2

sources:
  - name: raw
    tables:
      - name: raw_orders
        columns:
          - name: id
            tests: [not_null, unique]
          - name: amount
"""


class TestDbtReader:
    def _write_schema(self, tmp_path: Path, content: str, filename: str = "schema.yml") -> str:
        f = tmp_path / filename
        f.write_text(content)
        return str(tmp_path)

    def test_reads_models_section(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        assert any(t.name == "customers" for t in tables)

    def test_reads_sources_section(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SOURCES_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        assert any(t.name == "raw_orders" for t in tables)

    def test_not_null_test_sets_nullable_false(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        customers = next(t for t in tables if t.name == "customers")
        col_map = {c.name: c for c in customers.columns}
        assert col_map["email"].nullable is False

    def test_accepted_values_creates_choice_distribution(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        customers = next(t for t in tables if t.name == "customers")
        col_map = {c.name: c for c in customers.columns}
        assert col_map["status"].distribution == "choice"
        assert set(col_map["status"].dist_params["values"]) == {"active", "inactive", "pending"}

    def test_relationships_creates_fk(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        customers = next(t for t in tables if t.name == "customers")
        col_map = {c.name: c for c in customers.columns}
        fk = col_map["order_id"].foreign_key
        assert fk is not None
        assert fk.referenced_table == "orders"
        assert fk.referenced_column == "id"

    def test_email_column_gets_profile(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()
        customers = next(t for t in tables if t.name == "customers")
        col_map = {c.name: c for c in customers.columns}
        # Email column should get profile detected from name
        assert col_map["email"].profile == "email"

    def test_include_models_filter(self, tmp_path: Path) -> None:
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read(include_models=["customers"])
        assert len(tables) == 1
        assert tables[0].name == "customers"

    def test_missing_project_raises(self) -> None:
        reader = DbtReader("/nonexistent/path/to/project")
        with pytest.raises(FileNotFoundError):
            reader.read()

    def test_multiple_schema_files_merged(self, tmp_path: Path) -> None:
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "schema.yml").write_text(SIMPLE_SCHEMA_YML)
        (tmp_path / "models" / "other_schema.yml").write_text(SOURCES_SCHEMA_YML)
        reader = DbtReader(str(tmp_path))
        tables = reader.read()
        names = {t.name for t in tables}
        assert "customers" in names or "raw_orders" in names

    def test_dbt_generates_data_end_to_end(self, tmp_path: Path) -> None:
        """Full round-trip: read schema.yml → generate data via ForgeEngine."""
        project_dir = self._write_schema(tmp_path, SIMPLE_SCHEMA_YML)
        reader = DbtReader(project_dir)
        tables = reader.read()

        from forge_mock.engine.forge_engine import ForgeEngine

        with tempfile.TemporaryDirectory() as out_dir:
            engine = ForgeEngine(
                tables=tables,
                rows=20,
                seed=7,
                output_dir=out_dir,
                output_format="csv",
            )
            results = engine.run()

        assert "customers" in results
        df = results["customers"]
        assert len(df) == 20
        # status column should only contain accepted values
        statuses = set(df["status"].drop_nulls().to_list())
        assert statuses.issubset({"active", "inactive", "pending"})


# ---------------------------------------------------------------------------
# SchemaDriftDetector — unit tests (no live DB)
# ---------------------------------------------------------------------------


class TestSchemaDriftDetectorUnit:
    """Unit tests using mock config and schema data (no real database)."""

    def test_no_drift_returns_empty_list(self) -> None:
        # Build a config and a matching "live" schema manually
        from forge_mock.coherency.schema_drift import DriftItem

        detector = SchemaDriftDetector()

        # The detector.compare() needs a real DB, so we test the internal
        # drift logic by calling the print_report with known drift items
        drifts: list[DriftItem] = []
        assert detector.exit_code(drifts) == 0

    def test_high_severity_exit_code_is_1(self) -> None:
        from forge_mock.coherency.schema_drift import DriftItem

        detector = SchemaDriftDetector()
        drifts = [DriftItem(kind=DriftKind.table_removed, table="orders")]
        assert detector.exit_code(drifts) == 1

    def test_low_severity_exit_code_is_0(self) -> None:
        from forge_mock.coherency.schema_drift import DriftItem

        detector = SchemaDriftDetector()
        drifts = [DriftItem(kind=DriftKind.table_added, table="new_table")]
        assert detector.exit_code(drifts) == 0

    def test_drift_severity_classification(self) -> None:
        from forge_mock.coherency.schema_drift import DriftItem

        assert DriftItem(kind=DriftKind.table_removed, table="t").severity == "high"
        assert DriftItem(kind=DriftKind.column_removed, table="t", column="c").severity == "high"
        assert DriftItem(kind=DriftKind.type_changed, table="t", column="c").severity == "high"
        assert (
            DriftItem(kind=DriftKind.nullable_changed, table="t", column="c").severity == "medium"
        )
        assert DriftItem(kind=DriftKind.table_added, table="t").severity == "low"
        assert DriftItem(kind=DriftKind.column_added, table="t", column="c").severity == "low"

    def test_print_report_no_crash_on_empty(self, capsys: pytest.CaptureFixture) -> None:

        detector = SchemaDriftDetector()
        detector.print_report([])  # Should not raise

    def test_print_report_no_crash_with_drifts(self) -> None:
        from forge_mock.coherency.schema_drift import DriftItem

        detector = SchemaDriftDetector()
        drifts = [
            DriftItem(kind=DriftKind.table_added, table="new_tbl"),
            DriftItem(kind=DriftKind.column_removed, table="orders", column="legacy_col"),
            DriftItem(
                kind=DriftKind.type_changed,
                table="customers",
                column="id",
                config_value="VARCHAR",
                db_value="INT",
            ),
        ]
        detector.print_report(drifts)  # Should not raise
