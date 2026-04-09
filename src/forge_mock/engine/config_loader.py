"""YAML configuration loader for statistical distribution overrides."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

# Shape of the config file:
# tables:
#   orders:
#     rows: 10000
#     columns:
#       order_amount:
#         distribution: normal
#         mean: 50
#         std: 10
#       status:
#         distribution: choice
#         values: [pending, shipped, delivered, cancelled]


def load_config(path: Optional[str]) -> dict[str, Any]:
    """Load and validate a Forge YAML config file.

    Returns an empty dict if path is None.
    """
    if path is None:
        return {}

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        return {}

    return raw  # type: ignore[return-value]


def get_table_config(config: dict[str, Any], table_name: str) -> dict[str, Any]:
    """Extract per-table configuration."""
    return config.get("tables", {}).get(table_name, {})


def get_column_distribution(
    table_config: dict[str, Any], column_name: str
) -> tuple[Optional[str], dict[str, Any]]:
    """Return (distribution_name, params) for a column, or (None, {}) if not configured."""
    col_cfg = table_config.get("columns", {}).get(column_name, {})
    dist = col_cfg.get("distribution")
    if dist is None:
        return None, {}

    params = {k: v for k, v in col_cfg.items() if k != "distribution"}
    return str(dist), params


def get_row_count(table_config: dict[str, Any], default: int) -> int:
    return int(table_config.get("rows", default))
