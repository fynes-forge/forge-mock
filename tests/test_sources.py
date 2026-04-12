"""Tests for reference data sources and seed expander."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import numpy as np
import pytest

from forge_mock.sources.reference_source import ReferenceSource
from forge_mock.sources.seed_expander import SeedExpander


# ---------------------------------------------------------------------------
# ReferenceSource — CSV
# ---------------------------------------------------------------------------


class TestReferenceSourceCSV:
    def _make_csv(self, tmp_path: Path, rows: list[dict]) -> str:
        path = tmp_path / "data.csv"
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def test_random_draw_returns_value(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, [{"code": "A"}, {"code": "B"}, {"code": "C"}])
        src = ReferenceSource(csv_path, column="code", strategy="random")
        val = src.draw()
        assert val in ("A", "B", "C")

    def test_sequential_cycles(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, [{"v": "1"}, {"v": "2"}, {"v": "3"}])
        src = ReferenceSource(csv_path, column="v", strategy="sequential")
        results = [src.draw() for _ in range(6)]
        assert results == ["1", "2", "3", "1", "2", "3"]

    def test_random_deterministic_with_seed(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, [{"x": str(i)} for i in range(10)])
        rng = np.random.default_rng(99)
        src = ReferenceSource(csv_path, column="x", strategy="random", rng=rng)
        run1 = [src.draw() for _ in range(5)]

        rng2 = np.random.default_rng(99)
        src2 = ReferenceSource(csv_path, column="x", strategy="random", rng=rng2)
        run2 = [src2.draw() for _ in range(5)]
        assert run1 == run2

    def test_first_column_used_if_none_specified(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, [{"alpha": "X"}, {"alpha": "Y"}])
        src = ReferenceSource(csv_path)
        val = src.draw()
        assert val in ("X", "Y")

    def test_weighted_draw_respects_weights(self, tmp_path: Path) -> None:
        # Weight "A" heavily — should dominate
        rows = [
            {"code": "A", "weight": "100"},
            {"code": "B", "weight": "1"},
        ]
        csv_path = self._make_csv(tmp_path, rows)
        src = ReferenceSource(
            csv_path,
            column="code",
            strategy="weighted",
            weight_column="weight",
            rng=np.random.default_rng(0),
        )
        results = [src.draw() for _ in range(200)]
        assert results.count("A") > 150  # A should win overwhelmingly

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        bad_path = str(tmp_path / "data.xlsx")
        Path(bad_path).write_text("fake")
        src = ReferenceSource(bad_path, column="col")
        with pytest.raises(ValueError, match="Unsupported reference source format"):
            src.draw()

    def test_empty_source_returns_none(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, [{"v": ""}])
        # All values are empty — should return None
        src = ReferenceSource(csv_path, column="v")
        # Empty strings get filtered, so values list will be empty
        src._load()
        src._values = []  # force empty
        assert src.draw() is None


# ---------------------------------------------------------------------------
# ReferenceSource — Parquet
# ---------------------------------------------------------------------------


class TestReferenceSourceParquet:
    def _make_parquet(self, tmp_path: Path) -> str:
        import polars as pl

        df = pl.DataFrame({"sku": ["SKU001", "SKU002", "SKU003", "SKU004"]})
        path = str(tmp_path / "skus.parquet")
        df.write_parquet(path)
        return path

    def test_parquet_random_draw(self, tmp_path: Path) -> None:
        pq_path = self._make_parquet(tmp_path)
        src = ReferenceSource(pq_path, column="sku", strategy="random")
        val = src.draw()
        assert val in ("SKU001", "SKU002", "SKU003", "SKU004")

    def test_parquet_sequential(self, tmp_path: Path) -> None:
        pq_path = self._make_parquet(tmp_path)
        src = ReferenceSource(pq_path, column="sku", strategy="sequential")
        first_four = [src.draw() for _ in range(4)]
        assert first_four == ["SKU001", "SKU002", "SKU003", "SKU004"]

    def test_parquet_bad_column_raises(self, tmp_path: Path) -> None:
        pq_path = self._make_parquet(tmp_path)
        src = ReferenceSource(pq_path, column="nonexistent_col")
        with pytest.raises(ValueError, match="Column"):
            src.draw()


# ---------------------------------------------------------------------------
# SeedExpander
# ---------------------------------------------------------------------------


class TestSeedExpander:
    def _make_seed_csv(self, tmp_path: Path) -> str:
        path = tmp_path / "seeds.csv"
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["id", "name", "amount"])
            writer.writeheader()
            writer.writerows(
                [
                    {"id": "1", "name": "Alice", "amount": "100.0"},
                    {"id": "2", "name": "Bob", "amount": "200.0"},
                ]
            )
        return str(path)

    def test_expand_factor_applied(self, tmp_path: Path) -> None:
        csv_path = self._make_seed_csv(tmp_path)
        expander = SeedExpander(csv_path, expand_factor=5)
        rows = expander.expand()
        assert len(rows) == 10  # 2 seeds × 5

    def test_preserve_keeps_value(self, tmp_path: Path) -> None:
        csv_path = self._make_seed_csv(tmp_path)
        expander = SeedExpander(
            csv_path,
            expand_factor=3,
            column_mutations={"name": "preserve"},
        )
        rows = expander.expand()
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Bob"}  # all preserved

    def test_regenerate_changes_id(self, tmp_path: Path) -> None:
        csv_path = self._make_seed_csv(tmp_path)
        expander = SeedExpander(
            csv_path,
            expand_factor=10,
            column_mutations={"id": "regenerate"},
        )
        rows = expander.expand()
        ids = [r["id"] for r in rows]
        # At least some IDs should differ from the originals
        assert set(ids) - {"1", "2"}, "All regenerated IDs were the same as originals"

    def test_mutate_changes_numeric(self, tmp_path: Path) -> None:
        csv_path = self._make_seed_csv(tmp_path)
        expander = SeedExpander(
            csv_path,
            expand_factor=20,
            column_mutations={"amount": "mutate"},
            rng=np.random.default_rng(0),
        )
        rows = expander.expand()
        amounts = [float(r["amount"]) for r in rows]
        # Not all amounts should be exactly 100.0 or 200.0
        originals = {100.0, 200.0}
        non_originals = [a for a in amounts if a not in originals]
        assert len(non_originals) > 0

    def test_output_has_all_columns(self, tmp_path: Path) -> None:
        csv_path = self._make_seed_csv(tmp_path)
        expander = SeedExpander(csv_path, expand_factor=2)
        rows = expander.expand()
        for row in rows:
            assert set(row.keys()) == {"id", "name", "amount"}


# ---------------------------------------------------------------------------
# Engine integration — profile + source through ForgeEngine
# ---------------------------------------------------------------------------


class TestEngineWithProfiles:
    def test_profile_column_generates_emails(self) -> None:
        from forge_mock.engine.forge_engine import ForgeEngine
        from forge_mock.parser.schema_models import ColumnSchema, TableSchema

        col = ColumnSchema(
            name="email",
            sql_type="VARCHAR",
            base_type="VARCHAR",
            profile="email",
        )
        pk = ColumnSchema(
            name="id",
            sql_type="INT",
            base_type="INT",
            is_primary_key=True,
            nullable=False,
        )
        table = TableSchema(name="users", dialect="test", columns=[pk, col])

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(
                tables=[table], rows=20, seed=42, output_dir=tmpdir, output_format="csv"
            )
            results = engine.run()

        emails = results["users"]["email"].to_list()
        assert all("@" in str(e) for e in emails if e is not None)

    def test_locale_faker_used(self) -> None:
        from forge_mock.engine.forge_engine import ForgeEngine
        from forge_mock.parser.schema_models import ColumnSchema, TableSchema

        col = ColumnSchema(name="name", sql_type="VARCHAR", base_type="VARCHAR")
        pk = ColumnSchema(
            name="id", sql_type="INT", base_type="INT", is_primary_key=True, nullable=False
        )
        table = TableSchema(name="people", dialect="test", columns=[pk, col], locale="ja_JP")

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ForgeEngine(
                tables=[table], rows=10, seed=1, output_dir=tmpdir, output_format="csv"
            )
            results = engine.run()
        assert len(results["people"]) == 10
