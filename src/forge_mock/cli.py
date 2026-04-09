"""forge-mock CLI — generate synthetic data from SQL DDL files."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="forge-mock",
    help="⚒  forge-mock: Statistically realistic synthetic data from SQL DDL files.",
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True, style="bold red")

BANNER = """\
[bold cyan]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
[/bold cyan][dim]  Synthetic data that respects your schema.[/dim]
"""


class OutputFormat(str, Enum):
    parquet = "parquet"
    csv = "csv"
    sql = "sql"


class Dialect(str, Enum):
    postgres = "postgres"
    snowflake = "snowflake"
    bigquery = "bigquery"
    trino = "trino"
    duckdb = "duckdb"
    mysql = "mysql"
    sqlite = "sqlite"


@app.command()
def generate(
    ddl: Path = typer.Argument(
        ...,
        help="Path to the SQL DDL file containing CREATE TABLE statements.",
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    rows: int = typer.Option(
        1000,
        "--rows", "-r",
        help="Number of rows to generate per table.",
        min=1,
        max=10_000_000,
    ),
    output: Path = typer.Option(
        Path("."),
        "--output", "-o",
        help="Output directory for generated files.",
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.parquet,
        "--format", "-f",
        help="Output file format.",
    ),
    dialect: Dialect = typer.Option(
        Dialect.postgres,
        "--dialect", "-d",
        help="SQL dialect of the DDL file.",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed", "-s",
        help="Random seed for reproducible output (great for CI/CD).",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config", "-c",
        help="Path to a YAML config file for statistical distribution overrides.",
    ),
    corrupt: Optional[float] = typer.Option(
        None,
        "--corrupt",
        help=(
            "Inject bad data at this rate (0.0–1.0) for pipeline resilience testing. "
            "E.g. --corrupt 0.05 corrupts ~5%% of values."
        ),
        min=0.0,
        max=1.0,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed schema info before generation.",
    ),
) -> None:
    """
    ⚒  Generate synthetic data from a SQL DDL file.

    \b
    Examples:
      forge-mock generate schema.sql --rows 5000 --format csv
      forge-mock generate schema.sql --seed 42 --config overrides.yaml
      forge-mock generate schema.sql --corrupt 0.05 --format sql
    """
    console.print(BANNER)

    # Validate optional config path
    config_path: Optional[str] = None
    if config is not None:
        if not config.exists():
            err_console.print(f"Config file not found: {config}")
            raise typer.Exit(1)
        config_path = str(config)

    # Run summary panel
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary.add_column("Key", style="dim")
    summary.add_column("Value", style="bold cyan")
    summary.add_row("DDL File", str(ddl))
    summary.add_row("Dialect", dialect.value)
    summary.add_row("Rows / table", f"{rows:,}")
    summary.add_row("Format", format.value)
    summary.add_row("Output dir", str(output))
    summary.add_row("Seed", str(seed) if seed is not None else "[dim]none (random)[/dim]")
    summary.add_row("Config", config_path or "[dim]none[/dim]")
    summary.add_row(
        "Corrupt rate",
        f"[red]{corrupt}[/red]" if corrupt else "[dim]none[/dim]",
    )
    console.print(Panel(summary, title="[bold]Run Configuration", border_style="cyan"))

    # --- Parse ---
    from forge_mock.parser.ddl_parser import DDLParser

    try:
        parser = DDLParser(dialect=dialect.value)
        tables = parser.parse_file(str(ddl))
    except Exception as exc:
        err_console.print(f"[bold red]Parse error:[/bold red] {exc}")
        raise typer.Exit(1)

    if not tables:
        console.print("[yellow]⚠  No CREATE TABLE statements found in the DDL file.[/yellow]")
        raise typer.Exit(0)

    if verbose:
        _print_schema_summary(tables)

    # --- Load config ---
    from forge_mock.engine.config_loader import load_config

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1)

    # --- Generate ---
    from forge_mock.engine.forge_engine import ForgeEngine

    engine = ForgeEngine(
        tables=tables,
        rows=rows,
        seed=seed,
        config=cfg,
        corrupt_rate=corrupt or 0.0,
        output_dir=str(output),
        output_format=format.value,
    )

    try:
        results = engine.run()
    except Exception as exc:
        err_console.print(f"[bold red]Generation error:[/bold red] {exc}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)

    # Results table
    result_table = Table(
        "Table", "Rows", "Columns", "File",
        box=box.ROUNDED,
        border_style="green",
        title="[bold green]Generated Datasets",
    )
    for tname, df in results.items():
        result_table.add_row(
            f"[cyan]{tname}[/cyan]",
            f"[yellow]{len(df):,}[/yellow]",
            str(df.width),
            f"[dim]{output}/{tname}.{format.value}[/dim]",
        )
    console.print(result_table)


@app.command()
def inspect(
    ddl: Path = typer.Argument(
        ...,
        help="DDL file to inspect.",
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    dialect: Dialect = typer.Option(Dialect.postgres, "--dialect", "-d"),
) -> None:
    """
    🔍 Inspect a DDL file and print the parsed schema without generating data.
    """
    from forge_mock.parser.ddl_parser import DDLParser

    parser = DDLParser(dialect=dialect.value)
    try:
        tables = parser.parse_file(str(ddl))
    except Exception as exc:
        err_console.print(f"Parse error: {exc}")
        raise typer.Exit(1)

    if not tables:
        console.print("[yellow]No tables found.[/yellow]")
        return

    _print_schema_summary(tables)


@app.command()
def version() -> None:
    """Print forge-mock version."""
    from forge_mock import __version__
    console.print(f"[bold cyan]forge-mock[/bold cyan] [yellow]{__version__}[/yellow]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_schema_summary(tables: list) -> None:  # type: ignore[type-arg]
    from forge_mock.parser.schema_models import TableSchema

    for table in tables:
        t: TableSchema = table
        tbl = Table(
            "Column", "SQL Type", "Base Type", "PK", "Nullable", "FK",
            box=box.SIMPLE_HEAVY,
            title=f"[bold cyan]{t.name}[/bold cyan] [dim]({t.dialect})[/dim]",
            border_style="blue",
        )
        for col in t.columns:
            fk_label = ""
            if col.foreign_key:
                fk_label = (
                    f"→ {col.foreign_key.referenced_table}"
                    f".{col.foreign_key.referenced_column}"
                )
            tbl.add_row(
                col.name,
                col.sql_type,
                col.base_type,
                "✓" if col.is_primary_key else "",
                "" if col.nullable else "NOT NULL",
                f"[yellow]{fk_label}[/yellow]",
            )
        console.print(tbl)


if __name__ == "__main__":
    app()
