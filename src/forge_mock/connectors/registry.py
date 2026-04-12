"""Registry mapping database URL schemes to connector implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge_mock.connectors.base import BaseConnector

# Maps URL scheme prefixes → (module_path, class_name, extras_name)
_REGISTRY: dict[str, tuple[str, str, str]] = {
    "postgresql": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "postgres"),
    "postgres": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "postgres"),
    "mysql": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "mysql"),
    "mysql+pymysql": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "mysql"),
    "sqlite": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "sqlite"),
    "snowflake": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "snowflake"),
    "bigquery": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "bigquery"),
    "trino": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "trino"),
    "duckdb": ("forge_mock.connectors.sqlalchemy_connector", "SQLAlchemyConnector", "duckdb"),
}


def get_connector(connection_url: str, batch_size: int = 1000) -> "BaseConnector":
    """Instantiate and return the correct connector for the given URL.

    Raises ImportError with a helpful install hint if the required driver
    is not installed. Raises ValueError for unrecognised URL schemes.
    """
    scheme = _parse_scheme(connection_url)
    entry = _REGISTRY.get(scheme)

    if entry is None:
        supported = ", ".join(sorted({s.split("+")[0] for s in _REGISTRY}))
        raise ValueError(f"Unsupported database scheme '{scheme}'. Supported: {supported}")

    module_path, class_name, extras = entry
    try:
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
    except ImportError as exc:
        raise ImportError(
            f"Missing driver for '{scheme}'. Install it with:\n"
            f"  uv add 'forge-mock[{extras}]'\n"
            f"  # or: pip install 'forge-mock[{extras}]'"
        ) from exc

    return cls(connection_url=connection_url, batch_size=batch_size)  # type: ignore[no-any-return]


def list_supported_dialects() -> list[str]:
    """Return deduplicated list of supported dialect names."""
    return sorted({s.split("+")[0] for s in _REGISTRY})


def _parse_scheme(url: str) -> str:
    """Extract the scheme from a database URL string."""
    if "://" not in url:
        raise ValueError(
            f"Invalid connection URL '{url}'. Expected format: scheme://user:pass@host/database"
        )
    return url.split("://")[0].lower()
