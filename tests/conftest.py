"""Shared pytest fixtures for the test suite."""

import pytest


@pytest.fixture()
def sample_config() -> dict[str, str]:
    """Return a minimal config dict for testing."""
    return {
        "APP_ENV": "test",
        "LOG_LEVEL": "DEBUG",
    }
