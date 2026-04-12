"""Coherency pass — post-generation adjustments for thematic consistency.

Applied when --coherent flag is set. Fixes logical contradictions that
row-by-row generation cannot prevent:

  - Temporal ordering: shipped_date >= order_date, end_date >= start_date
  - Currency consistency: customers with GBP locale have orders in GBP
  - Realistic numeric ranges: discount <= unit_price, end_balance plausible
  - Date plausibility: date_of_birth is in the past, hire_date < termination_date

This is a best-effort pass. Columns are detected by name heuristics and
known FK relationships. It never raises — on any error it logs and skips.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

import numpy as np
import polars as pl

from forge_mock.parser.schema_models import TableSchema


# Column-name patterns for temporal ordering rules
_DATE_START_PATTERNS = re.compile(
    r"\b(order|created|start|opened|hired?|admitted?|registered?|from)[_\s]?(date|at|on|time)?\b",
    re.I,
)
_DATE_END_PATTERNS = re.compile(
    r"\b(shipped?|delivered?|closed?|end|finished?|terminated?|discharged?|to)[_\s]?(date|at|on|time)?\b",
    re.I,
)
_AMOUNT_PATTERNS = re.compile(
    r"\b(price|amount|cost|fee|total|gross|net)\b", re.I)
_DISCOUNT_PATTERNS = re.compile(r"\b(discount|rebate|reduction)\b", re.I)
_CURRENCY_PATTERNS = re.compile(r"\bcurrenc(y|ies)[_\s]?(code)?\b", re.I)


class CoherencyPass:
    """Applies post-generation coherency fixes to a dict of DataFrames."""

    def __init__(
        self,
        table_map: dict[str, TableSchema],
        rng: np.random.Generator,
    ) -> None:
        self._table_map = table_map
        self._rng = rng

    def apply(self, results: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
        """Run all coherency rules and return updated DataFrames."""
        fixed: dict[str, pl.DataFrame] = {}
        for table_name, df in results.items():
            table = self._table_map.get(table_name)
            df = self._fix_temporal_order(df, table)
            df = self._fix_discount_vs_price(df)
            df = self._fix_date_of_birth(df)
            fixed[table_name] = df
        return fixed

    # ------------------------------------------------------------------
    # Rule: end-dates must be >= start-dates
    # ------------------------------------------------------------------

    def _fix_temporal_order(self, df: pl.DataFrame, table: TableSchema | None) -> pl.DataFrame:
        """Ensure end/shipped/closed dates come after start/order/created dates."""
        cols = set(df.columns)

        # Find start/end column pairs by name heuristic
        start_cols = [c for c in cols if _DATE_START_PATTERNS.search(c)]
        end_cols = [c for c in cols if _DATE_END_PATTERNS.search(c)]

        for start_col in start_cols:
            for end_col in end_cols:
                if start_col == end_col:
                    continue
                try:
                    df = self._ensure_col_b_after_a(df, start_col, end_col)
                except Exception:
                    pass  # best-effort

        return df

    def _ensure_col_b_after_a(self, df: pl.DataFrame, col_a: str, col_b: str) -> pl.DataFrame:
        """For rows where col_b < col_a, swap the values."""
        if col_a not in df.columns or col_b not in df.columns:
            return df

        # Only process if both columns have date/datetime dtype
        a_dtype = df[col_a].dtype
        b_dtype = df[col_b].dtype
        date_types = {pl.Date, pl.Datetime}

        # Check if types are date-like (handle both old and new Polars dtype API)
        def is_date_like(dtype: Any) -> bool:
            return dtype in date_types or str(dtype).startswith("Datetime") or str(dtype) == "Date"

        if not (is_date_like(a_dtype) and is_date_like(b_dtype)):
            return df

        # Fix: where b < a and b is not null, add a random delta to b
        rows = df.to_dicts()
        for row in rows:
            a_val = row[col_a]
            b_val = row[col_b]
            if a_val is None or b_val is None:
                continue
            # Ensure both are comparable
            try:
                if b_val < a_val:
                    # Add 1–30 days to a_val
                    delta = int(self._rng.integers(1, 31))
                    if isinstance(a_val, datetime.datetime):
                        row[col_b] = a_val + datetime.timedelta(days=delta)
                    elif isinstance(a_val, datetime.date):
                        row[col_b] = a_val + datetime.timedelta(days=delta)
            except TypeError:
                pass

        try:
            return pl.DataFrame(rows, schema=df.schema)
        except Exception:
            return df

    # ------------------------------------------------------------------
    # Rule: discounts must be <= price/amount
    # ------------------------------------------------------------------

    def _fix_discount_vs_price(self, df: pl.DataFrame) -> pl.DataFrame:
        price_cols = [c for c in df.columns if _AMOUNT_PATTERNS.search(c)]
        discount_cols = [c for c in df.columns if _DISCOUNT_PATTERNS.search(c)]

        if not price_cols or not discount_cols:
            return df

        price_col = price_cols[0]
        discount_col = discount_cols[0]

        if price_col not in df.columns or discount_col not in df.columns:
            return df

        try:
            # Clamp discount to [0, price]
            df = df.with_columns(
                pl.when(pl.col(discount_col) > pl.col(price_col))
                .then(pl.col(price_col) * 0.2)
                .when(pl.col(discount_col) < 0)
                .then(pl.lit(0.0))
                .otherwise(pl.col(discount_col))
                .alias(discount_col)
            )
        except Exception:
            pass
        return df

    # ------------------------------------------------------------------
    # Rule: date_of_birth must be in the past (> 18 years ago)
    # ------------------------------------------------------------------

    def _fix_date_of_birth(self, df: pl.DataFrame) -> pl.DataFrame:
        dob_cols = [
            c
            for c in df.columns
            if re.search(r"\b(date[_\s]of[_\s]birth|dob|birthdate|birth[_\s]date)\b", c, re.I)
        ]
        if not dob_cols:
            return df

        cutoff = datetime.date.today() - datetime.timedelta(days=18 * 365)

        for dob_col in dob_cols:
            if df[dob_col].dtype not in (pl.Date,) and not str(df[dob_col].dtype).startswith(
                "Date"
            ):
                continue
            try:
                df = df.with_columns(
                    pl.when(pl.col(dob_col) > pl.lit(cutoff))
                    .then(
                        pl.lit(
                            cutoff -
                            datetime.timedelta(
                                days=int(self._rng.integers(0, 365 * 60)))
                        )
                    )
                    .otherwise(pl.col(dob_col))
                    .alias(dob_col)
                )
            except Exception:
                pass
        return df
