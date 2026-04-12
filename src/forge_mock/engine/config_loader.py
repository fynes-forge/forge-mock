"""YAML configuration loader.

Supports:
  tables:
    orders:
      rows: 10000
      locale: en_GB           # table-level locale for coherent mode
      columns:
        order_amount:
          distribution: normal
          mean: 50
          std: 10
        status:
          distribution: choice
          values: [pending, shipped, delivered, cancelled]
        email:
          profile: email       # semantic profile (Phase 3)
        patient_id:
          source: patients.csv # reference data source (Phase 4)
          source_column: id
          source_strategy: random
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, cast

import yaml


def load_config(path: Optional[str]) -> dict[str, Any]:
    """Load a Forge YAML config file. Returns empty dict if path is None."""
    if path is None:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise TypeError(f"Config file must contain a top-level mapping: {path}")
    # Strip internal metadata keys written by forge-mock plan
    config = cast(dict[str, Any], raw)
    config.pop("_forge_mock", None)
    return config


def get_table_config(config: dict[str, Any], table_name: str) -> dict[str, Any]:
    tables = config.get("tables")
    if not isinstance(tables, dict):
        return {}
    table_cfg = tables.get(table_name)
    if not isinstance(table_cfg, dict):
        return {}
    return cast(dict[str, Any], table_cfg)


def get_table_locale(table_config: dict[str, Any]) -> Optional[str]:
    """Return the locale override for a table, or None."""
    locale = table_config.get("locale")
    return locale if isinstance(locale, str) else None


def get_column_config(table_config: dict[str, Any], column_name: str) -> dict[str, Any]:
    """Return the raw column config dict (all keys)."""
    columns = table_config.get("columns")
    if not isinstance(columns, dict):
        return {}
    col_cfg = columns.get(column_name)
    if not isinstance(col_cfg, dict):
        return {}
    return cast(dict[str, Any], col_cfg)


def get_column_distribution(
    table_config: dict[str, Any], column_name: str
) -> tuple[Optional[str], dict[str, Any]]:
    """Return (distribution_name, params) or (None, {})."""
    col_cfg = get_column_config(table_config, column_name)
    dist = col_cfg.get("distribution")
    if dist is None:
        return None, {}
    params = {k: v for k, v in col_cfg.items() if k != "distribution"}
    return str(dist), params


def get_column_profile(table_config: dict[str, Any], column_name: str) -> Optional[str]:
    """Return the semantic profile name for a column, or None."""
    profile = get_column_config(table_config, column_name).get("profile")
    return profile if isinstance(profile, str) else None


def get_column_source(
    table_config: dict[str, Any], column_name: str
) -> tuple[Optional[str], Optional[str], str]:
    """Return (source_path, source_column, strategy) for a reference source column."""
    col_cfg = get_column_config(table_config, column_name)
    source = col_cfg.get("source")
    source_column = col_cfg.get("source_column")
    source_strategy = col_cfg.get("source_strategy", "random")
    return (
        source if isinstance(source, str) else None,
        source_column if isinstance(source_column, str) else None,
        source_strategy if isinstance(source_strategy, str) else "random",
    )


def get_row_count(table_config: dict[str, Any], default: int) -> int:
    return int(table_config.get("rows", default))
