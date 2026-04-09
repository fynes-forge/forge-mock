"""High-level column value generator combining Faker, distributions, and FK pools."""

from __future__ import annotations

import random
from typing import Any, Callable, Optional

import numpy as np
from faker import Faker

from forge_mock.generators.distribution_generator import DistributionGenerator
from forge_mock.generators.type_map import TYPE_GENERATOR_MAP
from forge_mock.parser.schema_models import ColumnSchema


class ColumnGenerator:
    """Generates a single value for a ColumnSchema, respecting FK pools and distributions."""

    def __init__(
        self,
        faker: Faker,
        rng: np.random.Generator,
        fk_pools: Optional[dict[str, list[Any]]] = None,
        corrupt_rate: float = 0.0,
    ) -> None:
        self._faker = faker
        self._rng = rng
        self._dist_gen = DistributionGenerator(rng)
        self._fk_pools: dict[str, list[Any]] = fk_pools or {}
        self._corrupt_rate = corrupt_rate
        # Per-column unique value tracking
        self._seen_unique: dict[str, set[Any]] = {}

    def generate(self, col: ColumnSchema) -> Any:
        """Generate one value for the given column."""
        # Schema-drift / corruption injection
        if self._corrupt_rate > 0.0 and random.random() < self._corrupt_rate:
            return self._inject_corruption(col)

        # NULL injection for nullable columns (~5% chance by default)
        if col.nullable and not col.is_primary_key and random.random() < 0.05:
            return None

        # Foreign key → pull from referenced pool
        if col.foreign_key is not None:
            pool_key = f"{col.foreign_key.referenced_table}.{col.foreign_key.referenced_column}"
            pool = self._fk_pools.get(pool_key, [])
            if pool:
                idx = int(self._rng.integers(0, len(pool)))
                return pool[idx]

        # Distribution override
        if col.distribution:
            return self._dist_gen.build(col.distribution, col.dist_params)

        # Type-based generation
        value = self._generate_by_type(col)

        # Ensure uniqueness for PK / UNIQUE columns
        if col.is_primary_key or col.is_unique:
            value = self._ensure_unique(col.name, value, col)

        return value

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_by_type(self, col: ColumnSchema) -> Any:
        factory_fn = TYPE_GENERATOR_MAP.get(col.base_type, TYPE_GENERATOR_MAP["VARCHAR"])
        generator = factory_fn(self._faker, col.type_params)
        return generator()

    def _ensure_unique(self, col_name: str, initial_value: Any, col: ColumnSchema) -> Any:
        seen = self._seen_unique.setdefault(col_name, set())
        value = initial_value
        attempts = 0
        while value in seen and attempts < 1000:
            value = self._generate_by_type(col)
            attempts += 1
        seen.add(value)
        return value

    def _inject_corruption(self, col: ColumnSchema) -> Any:
        """Inject bad data for resilience testing."""
        strategies: list[Callable[[], Any]] = [
            lambda: None,  # NULL in non-nullable
            lambda: "CORRUPT_VALUE",  # Type mismatch
            lambda: -999_999,  # Out-of-range integer
            lambda: "9999-99-99",  # Invalid date
            lambda: "",  # Empty string
            lambda: "\x00\x01\x02",  # Control chars
        ]
        strategy = random.choice(strategies)
        return strategy()
