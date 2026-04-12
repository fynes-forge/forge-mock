"""Content sampler — reads a small number of live rows to aid profile detection.

Instead of analysing column names alone, the sampler pulls 10–50 rows
from each column and passes the values to the PIIDetector for pattern matching.
This dramatically improves accuracy on columns with uninformative names
like `col1`, `field_a`, or abbreviated names like `ph_no`.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class ContentSampler:
    """Draws sample values from a live database table column."""

    def __init__(self, engine: "Engine", sample_size: int = 50) -> None:
        self._engine = engine
        self._sample_size = sample_size

    def sample_column(
        self,
        table_name: str,
        column_name: str,
        schema: Optional[str] = None,
    ) -> list[Any]:
        """Return up to `sample_size` non-null distinct values from the column.

        Returns an empty list if the table is empty or the column has no data.
        """
        from sqlalchemy import text

        qualified = f"{schema}.{table_name}" if schema else table_name
        query = text(
            f'SELECT DISTINCT "{column_name}" '
            f"FROM {qualified} "
            f'WHERE "{column_name}" IS NOT NULL '
            f"LIMIT :n"
        )
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(query, {"n": self._sample_size}).fetchall()
            return [row[0] for row in rows]
        except Exception:
            return []

    def sample_table(
        self,
        table_name: str,
        column_names: list[str],
        schema: Optional[str] = None,
    ) -> dict[str, list[Any]]:
        """Sample all given columns from a table in a single query.

        Returns a dict of {column_name: [values]}.
        Falls back to empty lists on error.
        """
        from sqlalchemy import text

        qualified = f"{schema}.{table_name}" if schema else table_name
        col_list = ", ".join(f'"{c}"' for c in column_names)

        query = text(f"SELECT {col_list} FROM {qualified} ORDER BY RANDOM() LIMIT :n")
        result: dict[str, list[Any]] = {c: [] for c in column_names}
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(query, {"n": self._sample_size}).fetchall()
            for row in rows:
                for i, col_name in enumerate(column_names):
                    if row[i] is not None:
                        result[col_name].append(row[i])
        except Exception:
            pass  # Return empty lists — sampling is best-effort
        return result
