"""NumPy-backed statistical distribution generators."""
from __future__ import annotations

from typing import Any

import numpy as np


class DistributionGenerator:
    """Generates values from named statistical distributions using NumPy."""

    SUPPORTED = frozenset(
        {
            "normal",
            "uniform",
            "poisson",
            "exponential",
            "lognormal",
            "binomial",
            "beta",
            "gamma",
            "choice",
            "integer_range",
        }
    )

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def build(self, distribution: str, params: dict[str, Any]) -> Any:
        """Generate a single value from the named distribution."""
        dist = distribution.lower()
        if dist not in self.SUPPORTED:
            raise ValueError(
                f"Unknown distribution '{distribution}'. "
                f"Supported: {sorted(self.SUPPORTED)}"
            )
        method = getattr(self, f"_dist_{dist}")
        return method(**params)

    # ------------------------------------------------------------------
    # Distribution implementations
    # ------------------------------------------------------------------

    def _dist_normal(self, mean: float = 0.0, std: float = 1.0, decimals: int = 4) -> float:
        return round(float(self._rng.normal(loc=mean, scale=std)), decimals)

    def _dist_uniform(self, low: float = 0.0, high: float = 1.0, decimals: int = 4) -> float:
        return round(float(self._rng.uniform(low=low, high=high)), decimals)

    def _dist_poisson(self, lam: float = 5.0) -> int:
        return int(self._rng.poisson(lam=lam))

    def _dist_exponential(self, scale: float = 1.0, decimals: int = 4) -> float:
        return round(float(self._rng.exponential(scale=scale)), decimals)

    def _dist_lognormal(self, mean: float = 0.0, sigma: float = 1.0, decimals: int = 4) -> float:
        return round(float(self._rng.lognormal(mean=mean, sigma=sigma)), decimals)

    def _dist_binomial(self, n: int = 1, p: float = 0.5) -> int:
        return int(self._rng.binomial(n=n, p=p))

    def _dist_beta(self, a: float = 2.0, b: float = 2.0, decimals: int = 6) -> float:
        return round(float(self._rng.beta(a=a, b=b)), decimals)

    def _dist_gamma(self, shape: float = 2.0, scale: float = 1.0, decimals: int = 4) -> float:
        return round(float(self._rng.gamma(shape=shape, scale=scale)), decimals)

    def _dist_choice(self, values: list[Any]) -> Any:
        idx = int(self._rng.integers(0, len(values)))
        return values[idx]

    def _dist_integer_range(self, low: int = 0, high: int = 100) -> int:
        return int(self._rng.integers(low=low, high=high, endpoint=True))
