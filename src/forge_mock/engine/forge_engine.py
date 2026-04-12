"""Core data generation engine orchestrating parsing, dependency resolution, and output."""

from __future__ import annotations

import dataclasses
import datetime
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
    get_column_profile,
    get_column_source,
    get_row_count,
    get_table_config,
    get_table_locale,
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
        locale: Optional[str] = None,
        coherent: bool = False,
        reference_sources: Optional[dict[str, Any]] = None,
    ) -> None:
        self._tables = tables
        self._rows = rows
        self._seed = seed
        self._config = config or {}
        self._corrupt_rate = corrupt_rate
        self._output_dir = Path(output_dir)
        self._output_format = output_format.lower()
        self._global_locale = locale
        self._coherent = coherent
        self._ref_sources: dict[str, Any] = reference_sources or {}

        # Seed RNG + Faker
        self._rng = np.random.default_rng(seed)
        self._faker = Faker(locale or "en_US")
        if seed is not None:
            Faker.seed(seed)

        # FK pools: "table.column" → list of generated values
        self._fk_pools: dict[str, list[Any]] = {}

        # Per-table Faker instances
        self._table_fakers: dict[str, Faker] = {}

        # Dependency resolution
        self._dep_graph = DependencyGraph()
        self._dep_graph.build(tables)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict[str, pl.DataFrame]:
        """Generate data for all tables in dependency order."""
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

                df = self._generate_table(table, table_cfg, n_rows, progress)
                results[table_name] = df

                # FIX: Populate pools so child tables can satisfy Foreign Keys
                self._populate_fk_pools(table, df)

                self._write_output(table_name, df)
                progress.advance(main_task)

        if self._coherent:
            results = self._apply_coherency(results, table_map)

        console.print(
            f"\n[bold green]✓ Done.[/bold green] Generated [yellow]{len(results)}[/yellow] table(s)"
        )
        return results

    # ------------------------------------------------------------------
    # Table generation
    # ------------------------------------------------------------------

    def _generate_table(
        self,
        table: TableSchema,
        table_cfg: dict[str, Any],
        n_rows: int,
        progress: Optional[Progress] = None,
    ) -> pl.DataFrame:
        """Generate n_rows for a table, honouring all config overrides."""
        columns = self._apply_config_overrides(table.columns, table_cfg)
        faker = self._get_faker_for_table(table, table_cfg)
        ref_sources = self._build_ref_sources(columns)

        col_gen = ColumnGenerator(
            faker=faker,
            rng=self._rng,
            fk_pools=self._fk_pools,  # Shares the central pool
            corrupt_rate=self._corrupt_rate,
            reference_sources=ref_sources,
        )

        data: dict[str, list[Any]] = {col.name: [] for col in columns}

        row_task = None
        if progress is not None and n_rows >= 10_000:
            row_task = progress.add_task(f"  [dim]{table.name}[/dim]", total=n_rows)

        # Main generation loop
        for i in range(n_rows):
            for col in columns:
                val = col_gen.generate(col)

                # --- FIX: Type Guard for SQLite Integrity ---
                # If the column is an INTEGER but ColumnGenerator returned a string
                # (likely due to a PII 'id' match), force it back to a valid numeric index.
                if col.base_type == "INTEGER" and not isinstance(val, (int, float, np.integer)):
                    val = i + 1

                data[col.name].append(val)

            if progress and row_task and i % max(1, n_rows // 100) == 0:
                progress.advance(row_task, max(1, n_rows // 100))

        if progress and row_task:
            progress.remove_task(row_task)

        return pl.DataFrame(
            {
                name: self._cast_series(name, values, _get_col(columns, name))
                for name, values in data.items()
            }
        )

    def _populate_fk_pools(self, table: TableSchema, df: pl.DataFrame) -> None:
        """Harvest generated PK/Unique values for Foreign Key resolution."""
        for col in table.columns:
            if col.is_primary_key or col.is_unique:
                # Key format matches ColumnGenerator expectations
                pool_key = f"{table.name}.{col.name}"
                if col.name in df.columns:
                    self._fk_pools[pool_key] = df[col.name].to_list()

    def _get_faker_for_table(self, table: TableSchema, table_cfg: dict[str, Any]) -> Faker:
        if table.name in self._table_fakers:
            return self._table_fakers[table.name]

        locale = table.locale or get_table_locale(table_cfg) or self._global_locale or "en_US"
        faker = Faker(locale)
        if self._seed is not None:
            faker.seed_instance(self._seed)
        self._table_fakers[table.name] = faker
        return faker

    def _apply_config_overrides(
        self, columns: list[ColumnSchema], table_cfg: dict[str, Any]
    ) -> list[ColumnSchema]:
        result = []
        for col in columns:
            updates: dict[str, Any] = {}
            dist, params = get_column_distribution(table_cfg, col.name)
            if dist:
                updates["distribution"] = dist
                updates["dist_params"] = params

            profile = get_column_profile(table_cfg, col.name)
            if profile:
                updates["profile"] = profile

            src, src_col, src_strategy = get_column_source(table_cfg, col.name)
            if src:
                updates["source"] = src
                updates["source_column"] = src_col
                updates["source_strategy"] = src_strategy

            if updates:
                col = dataclasses.replace(col, **updates)
            result.append(col)
        return result

    def _build_ref_sources(self, columns: list[ColumnSchema]) -> dict[str, Any]:
        from forge_mock.sources.reference_source import ReferenceSource

        sources: dict[str, Any] = dict(self._ref_sources)
        for col in columns:
            if col.source and col.source not in sources:
                try:
                    sources[col.source] = ReferenceSource(
                        path=col.source,
                        column=col.source_column,
                        strategy=col.source_strategy,
                        rng=self._rng,
                    )
                except Exception as exc:
                    console.log(f"[yellow]⚠  Could not load source '{col.source}': {exc}[/yellow]")
        return sources

    def _cast_series(
        self, col_name: str, values: list[Any], col: Optional[ColumnSchema]
    ) -> pl.Series:
        try:
            return pl.Series(col_name, values)
        except Exception:
            return pl.Series(col_name, [str(v) if v is not None else None for v in values])

    def _apply_coherency(
        self, results: dict[str, pl.DataFrame], table_map: dict[str, TableSchema]
    ) -> dict[str, pl.DataFrame]:
        try:
            from forge_mock.coherency.coherency_pass import CoherencyPass

            passer = CoherencyPass(table_map, self._rng)
            return passer.apply(results)
        except Exception as exc:
            console.log(f"[yellow]⚠  Coherency pass skipped: {exc}[/yellow]")
            return results

    def _write_output(self, table_name: str, df: pl.DataFrame) -> None:
        fmt = self._output_format
        if fmt == "parquet":
            self._write_parquet(table_name, df)
        elif fmt == "csv":
            self._write_csv(table_name, df)
        elif fmt == "sql":
            self._write_sql(table_name, df)

    def _write_parquet(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.parquet"
        pq.write_table(df.to_arrow(), str(path), compression="snappy")
        console.log(f"  [dim]→ {path}[/dim]")

    def _write_csv(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.csv"
        df.write_csv(str(path))
        console.log(f"  [dim]→ {path}[/dim]")

    def _write_sql(self, table_name: str, df: pl.DataFrame) -> None:
        path = self._output_dir / f"{table_name}.sql"
        columns = df.columns
        col_list = ", ".join(f'"{c}"' for c in columns)

        with path.open("w", encoding="utf-8") as fh:
            gen_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            fh.write(f"-- Generated by forge-mock at {gen_time}Z\n\n")
            rows = df.to_dicts()
            for i in range(0, len(rows), 500):
                batch = rows[i : i + 500]
                vals_list = []
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
                        else:
                            vals.append(f"'{str(v).replace(chr(39), chr(39) * 2)}'")
                    vals_list.append(f"  ({', '.join(vals)})")
                fh.write(
                    f'INSERT INTO "{table_name}" ({col_list}) VALUES\n'
                    + ",\n".join(vals_list)
                    + ";\n\n"
                )
        console.log(f"  [dim]→ {path}[/dim]")


def _get_col(columns: list[ColumnSchema], name: str) -> Optional[ColumnSchema]:
    return next((c for c in columns if c.name == name), None)
