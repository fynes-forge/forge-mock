"""Tests for src/config.py."""

from unittest.mock import patch


def test_load_config_returns_dict() -> None:
    """load_config should return a dictionary."""
    from src.config import load_config

    with patch.dict("os.environ", {"APP_ENV": "test"}, clear=False):
        config = load_config()

    assert isinstance(config, dict)


def test_load_config_contains_app_env() -> None:
    """load_config should include APP_ENV when set."""
    from src.config import load_config

    with patch.dict("os.environ", {"APP_ENV": "test"}, clear=False):
        config = load_config()

    assert config["APP_ENV"] == "test"
