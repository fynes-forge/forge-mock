"""High-level column value generator combining Faker, distributions, profiles, FK pools."""

from __future__ import annotations

from typing import Any, Optional, Callable

import numpy as np
from faker import Faker

from forge_mock.generators.distribution_generator import DistributionGenerator
from forge_mock.generators.profiles import apply_profile
from forge_mock.generators.type_map import TYPE_GENERATOR_MAP
from forge_mock.parser.schema_models import ColumnSchema


class ColumnGenerator:
    """Generates a single value for a ColumnSchema.

    Priority order:
      1. Corruption injection (if --corrupt rate active)
      2. FK pool draw
      3. Reference data source
      4. Statistical distribution override
      5. NULL injection (for standard nullable columns)
      6. Semantic profile (e.g. "email", "nhs_number")
      7. Type-based Faker generation
    """

    def __init__(
        self,
        faker: Faker,
        rng: np.random.Generator,
        fk_pools: Optional[dict[str, list[Any]]] = None,
        corrupt_rate: float = 0.0,
        reference_sources: Optional[dict[str, Any]] = None,
    ) -> None:
        self._faker = faker
        self._rng = rng
        self._dist_gen = DistributionGenerator(rng)
        self._fk_pools: dict[str, list[Any]] = fk_pools or {}
        self._corrupt_rate = corrupt_rate
        self._ref_sources: dict[str, Any] = reference_sources or {}
        self._seen_unique: dict[str, set[Any]] = {}

    def generate(self, col: ColumnSchema) -> Any:
        """Generate one value for the given column."""
        # 1. Corruption injection
        if self._corrupt_rate > 0.0 and self._rng.random() < self._corrupt_rate:
            return self._inject_corruption(col)

        # 2. FK pool draw
        if col.foreign_key is not None:
            pool_key = f"{col.foreign_key.referenced_table}.{col.foreign_key.referenced_column}"
            pool = self._fk_pools.get(pool_key, [])
            if pool:
                idx = int(self._rng.integers(0, len(pool)))
                return pool[idx]

        # 3. Reference data source
        if col.source and col.source in self._ref_sources:
            value = self._ref_sources[col.source].draw(
                column=col.source_column,
                strategy=col.source_strategy,
            )
            if value is not None:
                return value

        # 4. Distribution override
        if col.distribution:
            return self._dist_gen.build(col.distribution, col.dist_params)

        # 5. NULL injection for nullable non-PK columns (~5%)
        if col.nullable and not col.is_primary_key and self._rng.random() < 0.05:
            return None

        # 6. Semantic profile
        if col.profile:
            try:
                value = apply_profile(col.profile, self._faker)
                if col.is_primary_key or col.is_unique:
                    value = self._ensure_unique(
                        col_name=col.name, initial_value=value, col=col, use_profile=True
                    )
                return value
            except ValueError:
                pass

        # 7. Type-based generation
        value = self._generate_by_type(col)
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

    def _ensure_unique(
        self,
        col_name: str,
        initial_value: Any,
        col: ColumnSchema,
        use_profile: bool = False,
    ) -> Any:
        seen = self._seen_unique.setdefault(col_name, set())
        value = initial_value
        attempts = 0
        while value in seen and attempts < 1000:
            if use_profile and col.profile:
                value = apply_profile(col.profile, self._faker)
            else:
                value = self._generate_by_type(col)
            attempts += 1
        seen.add(value)
        return value

    def _inject_corruption(self, col: ColumnSchema) -> Any:
        """Inject bad data for resilience testing."""
        # Using explicit Callable typing for the strategies to satisfy Mypy
        strategies: list[Callable[[], Any]] = [
            lambda: None,
            lambda: "CORRUPT_VALUE",
            lambda: -999_999,
            lambda: "9999-99-99",
            lambda: "",
            lambda: "\x00\x01\x02",
        ]
        idx = int(self._rng.integers(0, len(strategies)))
        # Mypy might still flag the call as untyped because of the lambda nature
        return strategies[idx]()
