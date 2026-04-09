"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest
from faker import Faker
import numpy as np


@pytest.fixture
def faker_instance() -> Faker:
    Faker.seed(0)
    return Faker()


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)
