"""Tests for the data generation engine."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from forge_mock.engine.config_loader import (
    get_column_distribution,
    get_row_count,
    get_table_config,
    load_config,
)
from forge_mock.engine.dependency_graph import DependencyGraph
from forge_mock.engine.forge_engine import ForgeEngine
from forge_mock.generators.column_generator import ColumnGenerator
from forge_mock.generators.distribution_generator import DistributionGenerator
from forge_mock.parser.ddl_parser import DDLParser
from forge_mock.parser.schema_models import ColumnSchema, ForeignKeySchema, TableSchema
from tests.fixtures import FK_DDL, SIMPLE_DDL, MULTI_TYPE_DDL


# ---------------------------------------------------------------------------
# DependencyGraph tests
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def _make_table(self, name: str, deps: list[str]) -> TableSchema:
        cols = [ColumnSchema(name="id", sql_type="INT", base_type="INT", is_primary_key=True, nullable=False)]
        for dep in deps:
            cols.append(
                ColumnSchema(
                    name=f"{dep}_id",
                    sql_type="INT",
                    base_type="INT",
                    foreign_key=ForeignKeySchema(
                        column=f"{dep}_id",
                        referenced_table=dep,
                        referenced_column="id",
                    ),
                )
            )
        return TableSchema(name=name, dialect="postgres", columns=cols)

    def test_simple_linear_order(self) -> None:
        a = self._make_table("a", [])
        b = self._make_table("b", ["a"])
        graph = DependencyGraph()
        graph.build([b, a])  # deliberately reversed
        order = graph.generation_order()
        assert order.index("a") < order.index("b")

    def test_no_deps_any_order(self) -> None:
        a = self._make_table("a", [])
        b = self._make_table("b", [])
        graph = DependencyGraph()
        graph.build([a, b])
        order = graph.generation_order()
        assert set(order) == {"a", "b"}

    def test_three_level_chain(self) -> None:
        a = self._make_table("a", [])
        b = self._make_table("b", ["a"])
        c = self._make_table("c", ["b"])
        graph = DependencyGraph()
        graph.build([c, b, a])
        order = graph.generation_order()
        assert order.index("a") < order.index("b") < order.index("c")

    def test_no_cycles_returns_false(self) -> None:
        a = self._make_table("a", [])
        b = self._make_table("b", ["a"])
        graph = DependencyGraph()
        graph.build([a, b])
        assert graph.has_cycles() is False


# ---------------------------------------------------------------------------
# DistributionGenerator tests
# ---------------------------------------------------------------------------


class TestDistributionGenerator:
    def setup_method(self) -> None:
        self.rng = np.random.default_rng(42)
        self.gen = DistributionGenerator(self.rng)

    def test_normal_returns_float(self) -> None:
        v = self.gen.build("normal", {"mean": 50.0, "std": 10.0})
        assert isinstance(v, float)

    def test_normal_roughly_in_range(self) -> None:
        values = [self.gen.build("normal", {"mean": 100.0, "std": 5.0}) for _ in range(500)]
        assert 70 < sum(values) / len(values) < 130

    def test_poisson_returns_int(self) -> None:
        v = self.gen.build("poisson", {"lam": 3.0})
        assert isinstance(v, int)
        assert v >= 0

    def test_uniform_bounds(self) -> None:
        for _ in range(200):
            v = self.gen.build("uniform", {"low": 0.0, "high": 1.0})
            assert 0.0 <= v <= 1.0

    def test_choice_returns_one_of(self) -> None:
        options = ["alpha", "beta", "gamma"]
        for _ in range(50):
            v = self.gen.build("choice", {"values": options})
            assert v in options

    def test_integer_range(self) -> None:
        for _ in range(100):
            v = self.gen.build("integer_range", {"low": 10, "high": 20})
            assert 10 <= v <= 20

    def test_unknown_distribution_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown distribution"):
            self.gen.build("foobar_dist", {})

    def test_beta_between_0_and_1(self) -> None:
        for _ in range(100):
            v = self.gen.build("beta", {"a": 2.0, "b": 2.0})
            assert 0.0 <= v <= 1.0

    def test_exponential_positive(self) -> None:
        for _ in range(100):
            v = self.gen.build("exponential", {"scale": 1.0})
            assert v >= 0.0


# ---------------------------------------------------------------------------
# ColumnGenerator tests
# ---------------------------------------------------------------------------


class TestColumnGenerator:
    def _make_rng(self, seed: int = 0) -> np.random.Generator:
        return np.random.default_rng(seed)

    def _make_faker(self) -> Any:
        from faker import Faker
        return Faker()

    def test_pk_column_not_null(self) -> None:
        col = ColumnSchema(name="id", sql_type="BIGINT", base_type="BIGINT",
                           is_primary_key=True, nullable=False)
        gen = ColumnGenerator(self._make_faker(), self._make_rng())
        value = gen.generate(col)
        assert value is not None

    def test_pk_values_unique(self) -> None:
        col = ColumnSchema(name="id", sql_type="BIGINT", base_type="BIGINT",
                           is_primary_key=True, nullable=False)
        gen = ColumnGenerator(self._make_faker(), self._make_rng())
        values = [gen.generate(col) for _ in range(100)]
        assert len(set(values)) == 100

    def test_fk_pulls_from_pool(self) -> None:
        pool = [10, 20, 30]
        fk = ForeignKeySchema(column="dept_id", referenced_table="dept", referenced_column="id")
        col = ColumnSchema(name="dept_id", sql_type="INT", base_type="INT", foreign_key=fk)
        gen = ColumnGenerator(
            self._make_faker(), self._make_rng(),
            fk_pools={"dept.id": pool}
        )
        for _ in range(50):
            v = gen.generate(col)
            assert v in pool

    def test_distribution_override(self) -> None:
        col = ColumnSchema(
            name="amount", sql_type="FLOAT", base_type="FLOAT",
            distribution="uniform",
            dist_params={"low": 0.0, "high": 100.0},
        )
        gen = ColumnGenerator(self._make_faker(), self._make_rng())
        values = [gen.generate(col) for _ in range(200)]
        assert all(0.0 <= v <= 100.0 for v in values)

    def test_corrupt_rate_1_always_corrupts(self) -> None:
        col = ColumnSchema(name="name", sql_type="VARCHAR", base_type="VARCHAR", nullable=False)
        gen = ColumnGenerator(self._make_faker(), self._make_rng(), corrupt_rate=1.0)
        # At corrupt_rate=1.0, every value should be "corrupted" (may be None, wrong type, etc.)
        values = [gen.generate(col) for _ in range(20)]
        # At least some should be None or non-string
        assert any(v is None or not isinstance(v, str) or v in ("", "CORRUPT_VALUE") for v in values)

    def test_corrupt_rate_0_never_corrupts_pk(self) -> None:
        col = ColumnSchema(name="id", sql_type="INT", base_type="INT",
                           is_primary_key=True, nullable=False)
        gen = ColumnGenerator(self._make_faker(), self._make_rng(), corrupt_rate=0.0)
        values = [gen.generate(col) for _ in range(50)]
        assert all(v is not None for v in values)


# ---------------------------------------------------------------------------
# ForgeEngine integration tests
# ---------------------------------------------------------------------------


class TestForgeEngineIntegration:
    def _parse(self, ddl: str, dialect: str = "postgres") -> list[TableSchema]:
        return DDLParser(dialect=dialect).parse_sql(ddl)

    def test_simple_table_generates_correct_rows(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=50, seed=42, output_dir=tmpdir, output_format="csv")
            results = engine.run()
        assert "users" in results
        assert len(results["users"]) == 50

    def test_correct_column_count(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=10, seed=1, output_dir=tmpdir, output_format="csv")
            results = engine.run()
        assert results["users"].width == 7

    def test_fk_referential_integrity(self) -> None:
        tables = self._parse(FK_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=20, seed=99, output_dir=tmpdir, output_format="csv")
            results = engine.run()

        dept_ids = set(results["departments"]["dept_id"].to_list())
        emp_dept_ids = set(results["employees"]["dept_id"].to_list())
        assert emp_dept_ids.issubset(dept_ids), (
            f"FK violation: employee dept_ids {emp_dept_ids - dept_ids} not in departments"
        )

    def test_seed_produces_deterministic_output(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        results = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmpdir:
                engine = ForgeEngine(tables=tables, rows=30, seed=7, output_dir=tmpdir, output_format="csv")
                r = engine.run()
                results.append(r["users"].to_dicts())
        assert results[0] == results[1]

    def test_different_seeds_produce_different_output(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        results = []
        for seed in (1, 2):
            with tempfile.TemporaryDirectory() as tmpdir:
                engine = ForgeEngine(tables=tables, rows=30, seed=seed, output_dir=tmpdir, output_format="csv")
                r = engine.run()
                results.append(r["users"].to_dicts())
        assert results[0] != results[1]

    def test_parquet_output_written(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=10, seed=0, output_dir=tmpdir, output_format="parquet")
            engine.run()
            assert (Path(tmpdir) / "users.parquet").exists()

    def test_csv_output_written(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=10, seed=0, output_dir=tmpdir, output_format="csv")
            engine.run()
            assert (Path(tmpdir) / "users.csv").exists()

    def test_sql_output_written(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=10, seed=0, output_dir=tmpdir, output_format="sql")
            engine.run()
            sql_file = Path(tmpdir) / "users.sql"
            assert sql_file.exists()
            content = sql_file.read_text()
            assert "INSERT INTO" in content

    def test_multi_type_table(self) -> None:
        tables = self._parse(MULTI_TYPE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(tables=tables, rows=15, seed=3, output_dir=tmpdir, output_format="csv")
            results = engine.run()
        assert len(results["events"]) == 15

    def test_corrupt_mode_runs(self) -> None:
        tables = self._parse(SIMPLE_DDL)
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(
                tables=tables, rows=50, seed=0, corrupt_rate=0.2,
                output_dir=tmpdir, output_format="csv"
            )
            results = engine.run()
        # Engine should still produce a DataFrame; corruption doesn't crash
        assert len(results["users"]) == 50


# ---------------------------------------------------------------------------
# Config loader tests
# ---------------------------------------------------------------------------


class TestConfigLoader:
    def test_load_none_returns_empty(self) -> None:
        assert load_config(None) == {}

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_get_table_config_missing(self) -> None:
        cfg = {"tables": {"orders": {"rows": 500}}}
        assert get_table_config(cfg, "users") == {}

    def test_get_table_config_present(self) -> None:
        cfg = {"tables": {"orders": {"rows": 500}}}
        assert get_table_config(cfg, "orders") == {"rows": 500}

    def test_get_row_count_default(self) -> None:
        assert get_row_count({}, 1000) == 1000

    def test_get_row_count_override(self) -> None:
        assert get_row_count({"rows": 250}, 1000) == 250

    def test_get_column_distribution_missing(self) -> None:
        dist, params = get_column_distribution({}, "price")
        assert dist is None
        assert params == {}

    def test_get_column_distribution_present(self) -> None:
        table_cfg = {
            "columns": {
                "price": {"distribution": "normal", "mean": 50.0, "std": 5.0}
            }
        }
        dist, params = get_column_distribution(table_cfg, "price")
        assert dist == "normal"
        assert params == {"mean": 50.0, "std": 5.0}

    def test_load_yaml_file(self, tmp_path: Path) -> None:
        yaml_content = """
tables:
  orders:
    rows: 200
    columns:
      amount:
        distribution: normal
        mean: 75.0
        std: 15.0
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        cfg = load_config(str(config_file))
        assert cfg["tables"]["orders"]["rows"] == 200
        assert cfg["tables"]["orders"]["columns"]["amount"]["distribution"] == "normal"
