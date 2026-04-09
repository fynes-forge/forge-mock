"""Core data generation engine orchestrating parsing, dependency resolution, and output."""

from __future__ import annotations

import datetime
import dataclasses
from pathlib import Path
from typing import Any, Optional

import numpy as np
import polars as pl
import pyarrow.parquet as pq
from faker import Faker
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from forge_mock.engine.config_loader import (
    get_column_distribution,
    get_row_count,
    get_table_config,
)
from forge_mock.engine.dependency_graph import DependencyGraph
from forge_mock.generators.column_generator import ColumnGenerator
from forge_mock.parser.schema_models import ColumnSchema, TableSchema

console = Console()


class ForgeEngine:
    """Orchestrates end-to-end synthetic data generation."""

    def __init__(
        self,
        tables: list[TableSchema],
        rows: int = 1000,
        seed: Optional[int] = None,
        config: Optional[dict[str, Any]] = None,
        corrupt_rate: float = 0.0,
        output_dir: str = ".",
        output_format: str = "parquet",
    ) -> None:
        self._tables = tables
        self._rows = rows
        self._seed = seed
        self._config = config or {}
        self._corrupt_rate = corrupt_rate
        self._output_dir = Path(output_dir)
        self._output_format = output_format.lower()

        # Initialise RNG + Faker with optional seed
        self._rng = np.random.default_rng(seed)
        self._faker = Faker()
        if seed is not None:
            # CRITICAL: Use seed_instance to lock the specific object's RNG
            # for consistency across different environments (CI/CD)
            self._faker.seed_instance(seed)

        # FK value pools: "table.column" → list of generated values
        self._fk_pools: dict[str, list[Any]] = {}

        # Dependency resolution
        self._dep_graph = DependencyGraph()
        self._dep_graph.build(tables)

    # ... [run and _generate_table methods remain unchanged] ...

    def run(self) -> dict[str, pl.DataFrame]:
        """Generate data for all tables and write output files."""
        order = self._dep_graph.generation_order()
        table_map = {t.name: t for t in self._tables}
        results: dict[str, pl.DataFrame] = {}
        self._output_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=False,
        ) as progress:
            main_task = progress.add_task("[bold]Forging tables…", total=len(order))

            for table_name in order:
                table = table_map.get(table_name)
                if table is None:
                    progress.advance(main_task)
                    continue

                table_cfg = get_table_config(self._config, table_name)
                n_rows = get_row_count(table_cfg, self._rows)

                progress.log(
                    f"[bold green]▶[/bold green] [cyan]{table_name}[/cyan] "
                    f"→ [yellow]{n_rows:,}[/yellow] rows"
                )

                df = self._generate_table(table, table_cfg, n_rows)
                results[table_name] = df
                self._populate_fk_pools(table, df)
                self._write_output(table_name, df)
                progress.advance(main_task)

        console.print(
            f"\n[bold green]✓ Done.[/bold green] "
            f"Generated [yellow]{len(results)}[/yellow] table(s) "
            f"in [dim]{self._output_dir}[/dim]"
        )
        return results

    def _generate_table(
        self, table: TableSchema, table_cfg: dict[str, Any], n_rows: int
    ) -> pl.DataFrame:
        columns = self._apply_config_overrides(table.columns, table_cfg)
        col_gen = ColumnGenerator(
            faker=self._faker,
            rng=self._rng,
            fk_pools=self._fk_pools,
            corrupt_rate=self._corrupt_rate,
        )

        data: dict[str, list[Any]] = {col.name: [] for col in columns}
        for _ in range(n_rows):
            for col in columns:
                data[col.name].append(col_gen.generate(col))

        return pl.DataFrame(
            {
                name: self._cast_series(name, values, _get_col(columns, name))
                for name, values in data.items()
            }
        )

    def _apply_config_overrides(
        self, columns: list[ColumnSchema], table_cfg: dict[str, Any]
    ) -> list[ColumnSchema]:
        result = []
        for col in columns:
            dist, params = get_column_distribution(table_cfg, col.name)
            if dist:
                col = dataclasses.replace(col, distribution=dist, dist_params=params)
            result.append(col)
        return result

    def _cast_series(
        self, col_name: str, values: list[Any], col: Optional[ColumnSchema]
    ) -> pl.Series:
        try:
            return pl.Series(col_name, values)
        except Exception:
            return pl.Series(col_name, [str(v) if v is not None else None for v in values])

    def _populate_fk_pools(self, table: TableSchema, df: pl.DataFrame) -> None:
        for col in table.columns:
            if col.is_primary_key or col.is_unique:
                pool_key = f"{table.name}.{col.name}"
                if col.name in df.columns:
                    self._fk_pools[pool_key] = df[col.name].to_list()

    def _write_output(self, table_name: str, df: pl.DataFrame) -> None:
        fmt = self._output_format
        if fmt == "parquet":
            self._write_parquet(table_name, df)
        elif fmt == "csv":
            self._write_csv(table_name, df)
        elif fmt == "sql":
            self._write_sql(table_name, df)
        else:
            raise ValueError(f"Unknown output format: {fmt}")

    def _write_parquet(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.parquet"
        arrow_table = df.to_arrow()
        pq.write_table(arrow_table, str(path), compression="snappy")
        console.log(f"  [dim]→ {path}[/dim]")

    def _write_csv(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.csv"
        df.write_csv(str(path))
        console.log(f"  [dim]→ {path}[/dim]")

    def _write_sql(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.sql"
        columns = df.columns
        col_list = ", ".join(f'"{c}"' for c in columns)

        # Fix deprecation warning and drift by using UTC explicitly
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with path.open("w", encoding="utf-8") as fh:
            fh.write(f"-- Generated by forge-mock at {now_str}\n")
            fh.write(f"-- Table: {table_name} | Rows: {len(df)}\n\n")

            batch_size = 500
            rows = df.to_dicts()
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                value_strings = []
                for row in batch:
                    vals = []
                    for col in columns:
                        v = row[col]
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, bool):
                            vals.append("TRUE" if v else "FALSE")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        elif isinstance(v, (datetime.date, datetime.datetime)):
                            vals.append(f"'{v}'")
                        elif isinstance(v, bytes):
                            vals.append(f"X'{v.hex()}'")
                        else:
                            escaped = str(v).replace("'", "''")
                            vals.append(f"'{escaped}'")
                    value_strings.append(f"  ({', '.join(vals)})")

                fh.write(
                    f'INSERT INTO "{table_name}" ({col_list}) VALUES\n'
                    + ",\n".join(value_strings)
                    + ";\n\n"
                )
        console.log(f"  [dim]→ {path}[/dim]")


def _get_col(columns: list[ColumnSchema], name: str) -> Optional[ColumnSchema]:
    for c in columns:
        if c.name == name:
            return c
    return None
