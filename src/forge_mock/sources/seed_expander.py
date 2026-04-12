"""Seed expander — generates large datasets by mutating a small set of golden records.

Given a CSV/Parquet of "golden records" (e.g. 100 known-good customers),
the expander generates N synthetic variants of each record with controlled
mutation: some fields stay exact, some are mutated slightly, some are
regenerated entirely.

Config usage:
  tables:
    customers:
      seed_records: data/golden_customers.csv
      expand_factor: 100      # produce 100 variants per golden record
      columns:
        customer_id:   { mutation: regenerate }   # always new PK
        email:         { mutation: mutate }        # slight variation
        full_name:     { mutation: preserve }      # keep original exactly
        postcode:      { mutation: mutate }
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from faker import Faker


MutationStrategy = str  # "preserve" | "mutate" | "regenerate"

_DEFAULT_MUTATION: MutationStrategy = "mutate"


class SeedExpander:
    """Expands a small set of seed records into a larger synthetic dataset."""

    def __init__(
        self,
        seed_path: str,
        expand_factor: int = 10,
        column_mutations: Optional[dict[str, MutationStrategy]] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        """
        Args:
            seed_path:         Path to a CSV or Parquet file of golden records.
            expand_factor:     Number of synthetic variants to produce per seed row.
            column_mutations:  Per-column mutation strategy overrides.
            rng:               NumPy random generator for reproducibility.
        """
        self._path = seed_path
        self._expand_factor = expand_factor
        self._mutations: dict[str, MutationStrategy] = column_mutations or {}
        self._rng = rng or np.random.default_rng()
        self._seed_rows: list[dict[str, Any]] = []
        self._loaded = False

    def load(self) -> None:
        """Load seed records from disk."""
        if self._loaded:
            return
        suffix = self._path.split(".")[-1].lower()
        if suffix == "csv":
            self._seed_rows = self._load_csv()
        elif suffix in ("parquet", "pq"):
            self._seed_rows = self._load_parquet()
        else:
            raise ValueError(f"Unsupported seed file format: .{suffix}")
        self._loaded = True

    def expand(self) -> list[dict[str, Any]]:
        """Return all expanded rows."""
        self.load()
        result: list[dict[str, Any]] = []
        for seed_row in self._seed_rows:
            for _ in range(self._expand_factor):
                result.append(self._mutate_row(seed_row))
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _mutate_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Apply per-column mutation strategies to produce one variant."""
        faker = Faker()

        out: dict[str, Any] = {}
        for col, val in row.items():
            strategy = self._mutations.get(col, _DEFAULT_MUTATION)
            if strategy == "preserve":
                out[col] = val
            elif strategy == "regenerate":
                out[col] = self._regenerate(col, val, faker)
            else:  # mutate
                out[col] = self._mutate_value(val, faker)
        return out

    def _mutate_value(self, value: Any, faker: Faker) -> Any:
        """Apply a slight variation to a value while keeping it plausible."""
        if value is None:
            return None
        if isinstance(value, str):
            # Replace one character or append a digit
            if len(value) > 2:
                pos = int(self._rng.integers(0, len(value)))
                chars = list(value)
                chars[pos] = str(int(self._rng.integers(0, 10)))
                return "".join(chars)
            return value + str(int(self._rng.integers(0, 100)))
        if isinstance(value, (int, float)):
            noise = float(self._rng.normal(0, abs(value) * 0.05 + 1))
            if isinstance(value, int):
                return max(0, int(value + round(noise)))
            return round(value + noise, 2)
        return value

    def _regenerate(self, col_name: str, original: Any, faker: Faker) -> Any:
        """Generate a completely fresh value, using PII detection as a hint."""
        from forge_mock.profiler.pii_detector import PIIDetector

        detector = PIIDetector()
        suggestion = detector.suggest(col_name)
        if suggestion:
            from forge_mock.generators.profiles import apply_profile

            return apply_profile(suggestion.profile, faker)
        # Fall back to same type regeneration
        if isinstance(original, int):
            return int(self._rng.integers(1, 2_147_483_647))
        if isinstance(original, float):
            return round(float(self._rng.uniform(0, 1000)), 2)
        if isinstance(original, str):
            return faker.lexify("?" * max(len(original), 8))
        return original

    def _load_csv(self) -> list[dict[str, Any]]:
        import csv

        with open(self._path, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _load_parquet(self) -> list[dict[str, Any]]:
        import polars as pl

        return pl.read_parquet(self._path).to_dicts()
