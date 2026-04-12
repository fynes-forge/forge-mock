"""Reference data sources — external lookup tables for niche column data.

Allows columns to draw values from real-world reference data:
  - CSV files (e.g., a list of SNOMED codes, product SKUs, NHS trusts)
  - Parquet files (e.g., a curated list of valid CUSIPs)
  - SQL queries against a live database (e.g., SELECT code FROM icd10_codes)

Selection strategies:
  - random     — draw uniformly at random (with replacement)
  - weighted   — draw proportionally to a weight column
  - sequential — cycle through rows in order (useful for deterministic tests)

Config usage:
  tables:
    diagnoses:
      columns:
        snomed_code:
          source: data/snomed_subset.csv
          source_column: code
          source_strategy: random
        product_id:
          source: data/products.parquet
          source_column: product_id
          source_strategy: weighted
          weight_column: popularity_score
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Iterator, Optional

import numpy as np


class ReferenceSource:
    """Loads a data file and serves values using the configured selection strategy."""

    def __init__(
        self,
        path: str,
        column: Optional[str] = None,
        strategy: str = "random",
        weight_column: Optional[str] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        self._path = Path(path)
        self._column = column
        self._strategy = strategy
        self._weight_column = weight_column
        self._rng = rng or np.random.default_rng()
        self._values: list[Any] = []
        self._weights: Optional[list[float]] = None
        self._cycle: Optional[Iterator[Any]] = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        suffix = self._path.suffix.lower()
        if suffix == ".csv":
            self._load_csv()
        elif suffix in (".parquet", ".pq"):
            self._load_parquet()
        else:
            raise ValueError(
                f"Unsupported reference source format '{suffix}'. Supported: .csv, .parquet"
            )
        if self._strategy == "sequential":
            self._cycle = itertools.cycle(self._values)
        self._loaded = True

    def _load_csv(self) -> None:
        import csv

        with self._path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        col = self._column or (reader.fieldnames[0] if reader.fieldnames else None)
        if col is None:
            raise ValueError(f"Cannot determine column from CSV {self._path}")

        self._values = [row[col] for row in rows if col in row and row[col]]

        if self._weight_column and self._weight_column in (reader.fieldnames or []):
            raw_weights = [float(row.get(self._weight_column, 1.0) or 1.0) for row in rows]
            total = sum(raw_weights)
            self._weights = [w / total for w in raw_weights]

    def _load_parquet(self) -> None:
        import polars as pl

        df = pl.read_parquet(str(self._path))

        col = self._column or df.columns[0]
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in {self._path}. Available: {df.columns}")
        self._values = df[col].drop_nulls().to_list()

        if self._weight_column and self._weight_column in df.columns:
            raw = df[self._weight_column].fill_null(1.0).to_list()
            total = sum(float(w) for w in raw)
            self._weights = [float(w) / total for w in raw]

    def draw(
        self,
        column: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> Any:
        """Draw one value from the source using the configured strategy.

        Returns None if the source is empty.
        """
        # Allow per-draw column/strategy override (from ColumnSchema)
        if column and column != self._column:
            self._column = column
            self._loaded = False
        if strategy and strategy != self._strategy:
            self._strategy = strategy
            self._cycle = None
            self._loaded = False

        self._load()
        if not self._values:
            return None

        if self._strategy == "sequential":
            return next(self._cycle)  # type: ignore[arg-type]

        if self._strategy == "weighted" and self._weights:
            idx = int(self._rng.choice(len(self._values), p=self._weights))
        else:
            idx = int(self._rng.integers(0, len(self._values)))

        return self._values[idx]

    @classmethod
    def from_sql(
        cls,
        connection_url: str,
        query: str,
        column: Optional[str] = None,
        strategy: str = "random",
        rng: Optional[np.random.Generator] = None,
    ) -> "SQLReferenceSource":
        """Create a reference source backed by a SQL query."""
        return SQLReferenceSource(
            connection_url=connection_url,
            query=query,
            column=column,
            strategy=strategy,
            rng=rng,
        )


class SQLReferenceSource:
    """Reference source that draws from a live SQL query result."""

    def __init__(
        self,
        connection_url: str,
        query: str,
        column: Optional[str] = None,
        strategy: str = "random",
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        self._url = connection_url
        self._query = query
        self._column = column
        self._strategy = strategy
        self._rng = rng or np.random.default_rng()
        self._values: list[Any] = []
        self._cycle: Optional[Iterator[Any]] = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        from sqlalchemy import create_engine, text

        engine = create_engine(self._url)
        with engine.connect() as conn:
            rows = conn.execute(text(self._query)).fetchall()
        engine.dispose()

        col_idx = 0
        if self._column and rows:
            keys = list(rows[0]._mapping.keys())
            if self._column in keys:
                col_idx = keys.index(self._column)

        self._values = [row[col_idx] for row in rows if row[col_idx] is not None]
        if self._strategy == "sequential":
            self._cycle = itertools.cycle(self._values)
        self._loaded = True

    def draw(self, column: Optional[str] = None, strategy: Optional[str] = None) -> Any:
        self._load()
        if not self._values:
            return None
        if self._strategy == "sequential":
            return next(self._cycle)  # type: ignore[arg-type]
        idx = int(self._rng.integers(0, len(self._values)))
        return self._values[idx]
