"""forge-mock CLI — generate synthetic data from SQL DDL files."""

from __future__ import annotations

import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import models for type hinting
from forge_mock.parser.schema_models import TableSchema

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


# ===========================================================================
# generate
# ===========================================================================


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
        1000, "--rows", "-r", help="Number of rows to generate per table.", min=1, max=10_000_000
    ),
    output: Path = typer.Option(
        Path("."), "--output", "-o", help="Output directory for generated files."
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.parquet, "--format", "-f", help="Output file format."
    ),
    dialect: Dialect = typer.Option(
        Dialect.postgres, "--dialect", "-d", help="SQL dialect of the DDL file."
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", "-s", help="Random seed for reproducible output."
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="YAML config file for distribution/profile overrides."
    ),
    corrupt: Optional[float] = typer.Option(
        None, "--corrupt", help="Inject bad data at this rate (0.0–1.0).", min=0.0, max=1.0
    ),
    tables: Optional[str] = typer.Option(
        None, "--tables", "-t", help="Comma-separated tables to generate. Defaults to all."
    ),
    locale: Optional[str] = typer.Option(
        None, "--locale", help="Faker locale for generated data (e.g. en_GB, fr_FR, ja_JP)."
    ),
    coherent: bool = typer.Option(
        False,
        "--coherent",
        help="Apply post-generation coherency pass (date ordering, discount clamping).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print generation plan without writing any files."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed schema info before generation."
    ),
) -> None:
    """
    ⚒  Generate synthetic data from a SQL DDL file.

    \b
    Examples:
      forge-mock generate schema.sql --rows 5000 --format csv
      forge-mock generate schema.sql --seed 42 --config overrides.yaml
      forge-mock generate schema.sql --corrupt 0.05 --format sql
      forge-mock generate schema.sql --locale en_GB --coherent
    """
    console.print(BANNER)

    config_path: Optional[str] = None
    if config is not None:
        if not config.exists():
            err_console.print(f"Config file not found: {config}")
            raise typer.Exit(1)
        config_path = str(config)

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
    summary.add_row("Locale", locale or "[dim]en_US[/dim]")
    summary.add_row("Coherent", "[green]yes[/green]" if coherent else "[dim]no[/dim]")
    summary.add_row("Corrupt rate", f"[red]{corrupt}[/red]" if corrupt else "[dim]none[/dim]")
    summary.add_row("Tables filter", tables or "[dim]all[/dim]")
    summary.add_row(
        "Dry run", "[yellow]yes — no files will be written[/yellow]" if dry_run else "[dim]no[/dim]"
    )
    console.print(Panel(summary, title="[bold]Run Configuration", border_style="cyan"))

    from forge_mock.parser.ddl_parser import DDLParser

    try:
        tables_list = DDLParser(dialect=dialect.value).parse_file(str(ddl))
    except Exception as exc:
        err_console.print(f"[bold red]Parse error:[/bold red] {exc}")
        raise typer.Exit(1)

    if not tables_list:
        console.print("[yellow]⚠  No CREATE TABLE statements found.[/yellow]")
        raise typer.Exit(0)

    if tables:
        requested = {t.strip() for t in tables.split(",")}
        available = {t.name for t in tables_list}
        unknown = requested - available
        if unknown:
            err_console.print(
                f"[bold red]Unknown tables:[/bold red] {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(available))}"
            )
            raise typer.Exit(1)
        tables_list = [t for t in tables_list if t.name in requested]

    if verbose:
        _print_schema_summary(tables_list)

    if dry_run:
        _print_dry_run_plan(tables_list, rows, format.value, str(output))
        raise typer.Exit(0)

    from forge_mock.engine.config_loader import load_config

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as exc:
        err_console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        err_console.print(
            f"[bold red]Config parse error:[/bold red] {exc}\nCheck your YAML syntax."
        )
        raise typer.Exit(1)

    from forge_mock.engine.forge_engine import ForgeEngine

    engine = ForgeEngine(
        tables=tables_list,
        rows=rows,
        seed=seed,
        config=cfg,
        corrupt_rate=corrupt or 0.0,
        output_dir=str(output),
        output_format=format.value,
        locale=locale,
        coherent=coherent,
    )
    try:
        results = engine.run()
    except Exception as exc:
        err_console.print(f"[bold red]Generation error:[/bold red] {exc}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)

    result_table = Table(
        "Table",
        "Rows",
        "Columns",
        "File",
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


# ===========================================================================
# connect
# ===========================================================================


@app.command()
def connect(
    connection_url: str = typer.Argument(
        ...,
        help="Database connection URL. e.g. postgresql://user:pass@host/db",
        envvar="FORGE_DATABASE_URL",
    ),
    rows: int = typer.Option(1000, "--rows", "-r", help="Rows per table.", min=1),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write files here instead of inserting into the database."
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.parquet, "--format", "-f", help="Output format when --output is set."
    ),
    insert_mode: str = typer.Option(
        "append", "--insert-mode", help="How to handle existing data: append | truncate | replace."
    ),
    batch_size: int = typer.Option(1000, "--batch-size", help="Rows per INSERT batch.", min=1),
    db_schema: Optional[str] = typer.Option(
        None, "--schema", help="Target database schema/namespace."
    ),
    tables: Optional[str] = typer.Option(
        None, "--tables", "-t", help="Comma-separated list of tables to populate. Defaults to all."
    ),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="YAML config for distribution overrides."
    ),
    corrupt: Optional[float] = typer.Option(
        None, "--corrupt", help="Corruption injection rate (0.0–1.0).", min=0.0, max=1.0
    ),
    locale: Optional[str] = typer.Option(
        None, "--locale", help="Faker locale (e.g. en_GB, fr_FR)."
    ),
    coherent: bool = typer.Option(
        False, "--coherent", help="Apply post-generation coherency pass."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Introspect and plan without generating or inserting."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show schema detail."),
) -> None:
    """
    🔌 Connect to a live database, introspect its schema, and populate it.

    \b
    Examples:
      forge-mock connect postgresql://user:pass@localhost/mydb --rows 1000
      forge-mock connect postgresql://user:pass@localhost/mydb --output ./data
      forge-mock connect $DATABASE_URL --tables orders,customers --seed 42
    """
    console.print(BANNER)

    from forge_mock.connectors.base import InsertMode
    from forge_mock.connectors.registry import get_connector
    from forge_mock.connectors.sqlalchemy_connector import _mask_url

    try:
        ins_mode = InsertMode(insert_mode)
    except ValueError:
        err_console.print(
            f"[bold red]Invalid --insert-mode '{insert_mode}'.[/bold red] "
            "Choose: append | truncate | replace"
        )
        raise typer.Exit(1)

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary.add_column("Key", style="dim")
    summary.add_column("Value", style="bold cyan")
    summary.add_row("Connection", _mask_url(connection_url))
    summary.add_row("Rows / table", f"{rows:,}")
    summary.add_row(
        "Insert mode", ins_mode.value if output is None else "[dim]n/a (file output)[/dim]"
    )
    summary.add_row("Batch size", str(batch_size) if output is None else "[dim]n/a[/dim]")
    summary.add_row("Output", str(output) if output else "[dim]insert into DB[/dim]")
    summary.add_row("Format", format.value if output else "[dim]n/a[/dim]")
    summary.add_row("Schema", db_schema or "[dim]default[/dim]")
    summary.add_row("Tables filter", tables or "[dim]all[/dim]")
    summary.add_row("Seed", str(seed) if seed is not None else "[dim]none[/dim]")
    summary.add_row("Dry run", "[yellow]yes[/yellow]" if dry_run else "[dim]no[/dim]")
    console.print(Panel(summary, title="[bold]Connect Configuration", border_style="cyan"))

    try:
        connector = get_connector(connection_url, batch_size=batch_size)
    except (ValueError, ImportError) as exc:
        err_console.print(f"[bold red]Connector error:[/bold red] {exc}")
        raise typer.Exit(1)

    with connector:
        if not connector.test_connection():
            err_console.print("[bold red]Could not connect to the database.[/bold red]")
            raise typer.Exit(1)
        console.print("[bold green]✓ Connected[/bold green]")

        include = [t.strip() for t in tables.split(",")] if tables else None
        try:
            tables_list = connector.introspect(schema=db_schema, include_tables=include)
        except Exception as exc:
            err_console.print(f"[bold red]Introspection error:[/bold red] {exc}")
            raise typer.Exit(1)

        if not tables_list:
            console.print("[yellow]⚠  No tables found in the database.[/yellow]")
            raise typer.Exit(0)

        if verbose:
            _print_schema_summary(tables_list)

        if dry_run:
            _print_dry_run_plan(
                tables_list,
                rows,
                format.value if output else "insert",
                str(output) if output else connection_url,
            )
            raise typer.Exit(0)

        from forge_mock.engine.config_loader import load_config

        try:
            cfg = load_config(str(config) if config else None)
        except Exception as exc:
            err_console.print(f"[bold red]Config error:[/bold red] {exc}")
            raise typer.Exit(1)

        from forge_mock.engine.forge_engine import ForgeEngine

        if output:
            engine = ForgeEngine(
                tables=tables_list,
                rows=rows,
                seed=seed,
                config=cfg,
                corrupt_rate=corrupt or 0.0,
                output_dir=str(output),
                output_format=format.value,
                locale=locale,
                coherent=coherent,
            )
            try:
                results = engine.run()
            except Exception as exc:
                err_console.print(f"[bold red]Generation error:[/bold red] {exc}")
                raise typer.Exit(1)
        else:
            engine = ForgeEngine(
                tables=tables_list,
                rows=rows,
                seed=seed,
                config=cfg,
                corrupt_rate=corrupt or 0.0,
                output_dir="/tmp/forge-mock-insert-staging",
                output_format="parquet",
                locale=locale,
                coherent=coherent,
            )
            try:
                results = engine.run()
            except Exception as exc:
                err_console.print(f"[bold red]Generation error:[/bold red] {exc}")
                raise typer.Exit(1)

            result_table = Table(
                "Table",
                "Rows inserted",
                "Mode",
                box=box.ROUNDED,
                border_style="green",
                title="[bold green]Insert Results",
            )
            for tname, df in results.items():
                try:
                    n = connector.insert(tname, df, mode=ins_mode, schema=db_schema)
                    result_table.add_row(
                        f"[cyan]{tname}[/cyan]",
                        f"[yellow]{n:,}[/yellow]",
                        ins_mode.value,
                    )
                except Exception as exc:
                    err_console.print(f"[bold red]Insert failed for {tname}:[/bold red] {exc}")
                    raise typer.Exit(1)
            console.print(result_table)
            return

    result_table = Table(
        "Table",
        "Rows",
        "Columns",
        "File",
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


# ===========================================================================
# pull-schema
# ===========================================================================


@app.command(name="pull-schema")
def pull_schema(
    connection_url: str = typer.Argument(
        ..., help="Database connection URL.", envvar="FORGE_DATABASE_URL"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write DDL to this file. Prints to stdout if not set."
    ),
    db_schema: Optional[str] = typer.Option(
        None, "--schema", help="Database schema/namespace to pull from."
    ),
    tables: Optional[str] = typer.Option(
        None, "--tables", "-t", help="Comma-separated list of tables to include. Defaults to all."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show schema detail."),
) -> None:
    """
    📥 Pull the live schema from a database and write it as a DDL file.
    """
    from forge_mock.connectors.registry import get_connector
    from forge_mock.connectors.sqlalchemy_connector import _mask_url, _table_to_ddl

    console.print(f"[bold cyan]Pulling schema from[/bold cyan] {_mask_url(connection_url)}")

    try:
        connector = get_connector(connection_url)
    except (ValueError, ImportError) as exc:
        err_console.print(f"[bold red]Connector error:[/bold red] {exc}")
        raise typer.Exit(1)

    with connector:
        if not connector.test_connection():
            err_console.print("[bold red]Could not connect to the database.[/bold red]")
            raise typer.Exit(1)

        include = [t.strip() for t in tables.split(",")] if tables else None
        try:
            if include:
                tables_list = connector.introspect(schema=db_schema, include_tables=include)

                # FIX: Pass table.name (str) instead of the table object (TableSchema)
                ddl_parts = [_table_to_ddl(t.name) for t in tables_list]

                ddl_text = "\n\n".join(
                    [
                        f"-- Schema pulled from {_mask_url(connection_url)}",
                        f"-- Generated by forge-mock at "
                        f"{datetime.datetime.now(datetime.timezone.utc).isoformat()}Z",
                    ]
                    + ddl_parts
                )
            else:
                ddl_text = connector.pull_ddl(schema=db_schema)
                tables_list = connector.introspect(schema=db_schema)
        except Exception as exc:
            err_console.print(f"[bold red]Schema pull error:[/bold red] {exc}")
            raise typer.Exit(1)

        if verbose:
            _print_schema_summary(tables_list)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(ddl_text, encoding="utf-8")
        console.print(
            f"[bold green]✓ Schema written to[/bold green] [dim]{output}[/dim] "
            f"([yellow]{len(tables_list)}[/yellow] tables)"
        )
    else:
        console.print(ddl_text)


# ===========================================================================
# inspect
# ===========================================================================


@app.command()
def inspect(
    ddl: Path = typer.Argument(
        ..., help="DDL file to inspect.", exists=True, readable=True, resolve_path=True
    ),
    dialect: Dialect = typer.Option(Dialect.postgres, "--dialect", "-d"),
) -> None:
    """
    🔍 Inspect a DDL file and print the parsed schema without generating data.
    """
    from forge_mock.parser.ddl_parser import DDLParser

    try:
        tables = DDLParser(dialect=dialect.value).parse_file(str(ddl))
    except Exception as exc:
        err_console.print(f"Parse error: {exc}")
        raise typer.Exit(1)

    if not tables:
        console.print("[yellow]No tables found.[/yellow]")
        return

    _print_schema_summary(tables)


# ===========================================================================
# plan
# ===========================================================================


@app.command()
def plan(
    connection_url: str = typer.Argument(
        ..., help="Database URL to introspect and plan against.", envvar="FORGE_DATABASE_URL"
    ),
    output: Path = typer.Option(
        Path("forge.yaml"), "--output", "-o", help="Where to write the generated forge.yaml config."
    ),
    rows: int = typer.Option(1000, "--rows", "-r", help="Default rows per table."),
    db_schema: Optional[str] = typer.Option(None, "--schema", help="Database schema."),
    tables: Optional[str] = typer.Option(
        None, "--tables", "-t", help="Comma-separated tables to plan. Defaults to all."
    ),
    sample_size: int = typer.Option(
        50, "--sample-size", help="Rows to sample per column for content-based PII detection."
    ),
    min_confidence: float = typer.Option(
        0.80, "--min-confidence", help="Minimum confidence threshold (0–1) to suggest a profile."
    ),
    auto_accept: bool = typer.Option(
        False, "--yes", "-y", help="Accept all suggestions without prompting (CI-friendly)."
    ),
) -> None:
    """
    🧠 Analyse a live database, detect PII/semantic column types, and write forge.yaml.
    """
    from forge_mock.connectors.registry import get_connector
    from forge_mock.connectors.sqlalchemy_connector import _mask_url
    from forge_mock.profiler.content_sampler import ContentSampler
    from forge_mock.profiler.forge_yaml_writer import write_forge_yaml
    from forge_mock.profiler.pii_detector import PIIDetector

    console.print(BANNER)
    console.print(f"[bold cyan]Planning schema from[/bold cyan] {_mask_url(connection_url)}\n")

    try:
        connector = get_connector(connection_url)
    except (ValueError, ImportError) as exc:
        err_console.print(f"[bold red]Connector error:[/bold red] {exc}")
        raise typer.Exit(1)

    sampler: Optional[ContentSampler] = None
    with connector:
        if not connector.test_connection():
            err_console.print("[bold red]Could not connect.[/bold red]")
            raise typer.Exit(1)

        include = [t.strip() for t in tables.split(",")] if tables else None
        try:
            tables_list = connector.introspect(schema=db_schema, include_tables=include)
        except Exception as exc:
            err_console.print(f"[bold red]Introspection error:[/bold red] {exc}")
            raise typer.Exit(1)

        try:
            from sqlalchemy import create_engine

            _engine = create_engine(connection_url)
            sampler = ContentSampler(_engine, sample_size=sample_size)
        except Exception:
            sampler = None

    detector = PIIDetector()
    plan_config: dict[str, Any] = {"tables": {}}

    for table in tables_list:
        console.rule(f"[bold cyan]{table.name}[/bold cyan]")
        table_plan: dict[str, Any] = {"rows": rows, "columns": {}}

        sample_cols = [
            c.name for c in table.columns if c.base_type in ("VARCHAR", "TEXT", "CHAR", "UUID")
        ]
        samples: dict[str, list[str]] = {}
        if sampler and sample_cols:
            try:
                samples = sampler.sample_table(table.name, sample_cols, schema=db_schema)
            except Exception:
                pass

        for col in table.columns:
            suggestion = detector.suggest(
                col.name,
                sampled_values=samples.get(col.name),
                min_confidence=min_confidence,
            )
            if suggestion is None:
                continue

            bar = "█" * int(suggestion.confidence * 10)
            console.print(
                f"  [cyan]{col.name}[/cyan]  "
                f"→  [bold yellow]{suggestion.profile}[/bold yellow]  "
                f"[dim]{bar} {suggestion.confidence:.0%}[/dim]  "
                f"[dim italic]{suggestion.reason}[/dim]"
            )

            accept = True
            if not auto_accept:
                accept = typer.confirm(
                    f"    Apply profile '{suggestion.profile}' to '{col.name}'?",
                    default=True,
                )
            if accept:
                table_plan["columns"][col.name] = {"profile": suggestion.profile}

        plan_config["tables"][table.name] = table_plan if table_plan["columns"] else {"rows": rows}

    try:
        write_forge_yaml(plan_config, str(output), connection_url)
        console.print(f"\n[bold green]✓ forge.yaml written to[/bold green] [dim]{output}[/dim]")
        console.print(
            f"  Run with: [bold]forge-mock connect "
            f"{_mask_url(connection_url)} --config {output}[/bold]"
        )
    except Exception as exc:
        err_console.print(f"[bold red]Failed to write forge.yaml:[/bold red] {exc}")
        raise typer.Exit(1)


# ===========================================================================
# diff
# ===========================================================================


@app.command()
def diff(
    config: Path = typer.Argument(
        ...,
        help="Path to forge.yaml config to compare against.",
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    connection_url: str = typer.Argument(
        ..., help="Database URL to compare against.", envvar="FORGE_DATABASE_URL"
    ),
    db_schema: Optional[str] = typer.Option(None, "--schema", help="Database schema."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit with code 1 on any drift (not just high severity)."
    ),
) -> None:
    """
    📊 Compare a forge.yaml config against a live database and report schema drift.
    """
    from forge_mock.coherency.schema_drift import SchemaDriftDetector
    from forge_mock.profiler.forge_yaml_writer import load_forge_yaml

    try:
        config_data = load_forge_yaml(str(config))
    except Exception as exc:
        err_console.print(f"[bold red]Could not load config:[/bold red] {exc}")
        raise typer.Exit(1)

    if not config_data.get("tables"):
        console.print("[yellow]⚠  Config has no tables section — nothing to compare.[/yellow]")
        raise typer.Exit(0)

    detector = SchemaDriftDetector()
    try:
        drifts = detector.compare(config_data, connection_url, db_schema=db_schema)
    except Exception as exc:
        err_console.print(f"[bold red]Drift detection error:[/bold red] {exc}")
        raise typer.Exit(1)

    detector.print_report(drifts)

    if strict and drifts:
        raise typer.Exit(1)
    raise typer.Exit(detector.exit_code(drifts))


# ===========================================================================
# dbt
# ===========================================================================


@app.command(name="dbt")
def dbt_command(
    project_dir: Path = typer.Argument(
        Path("."), help="Path to the dbt project root.", resolve_path=True
    ),
    rows: int = typer.Option(500, "--rows", "-r", help="Rows per model.", min=1),
    output: Path = typer.Option(
        Path("."), "--output", "-o", help="Output directory for generated files."
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.parquet, "--format", "-f", help="Output format."
    ),
    models: Optional[str] = typer.Option(
        None, "--models", "-m", help="Comma-separated dbt model names to generate. Defaults to all."
    ),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="Random seed."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Additional forge.yaml overrides."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan without generating."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show schema detail."),
) -> None:
    """
    🔧 Generate synthetic data from a dbt project's schema.yml files.
    """
    console.print(BANNER)
    console.print(f"[bold cyan]Reading dbt project from[/bold cyan] {project_dir}\n")

    from forge_mock.coherency.dbt_reader import DbtReader
    from forge_mock.engine.config_loader import load_config
    from forge_mock.engine.forge_engine import ForgeEngine

    include_models = [m.strip() for m in models.split(",")] if models else None

    try:
        tables_list = DbtReader(str(project_dir)).read(include_models=include_models)
    except FileNotFoundError as exc:
        err_console.print(f"[bold red]dbt project error:[/bold red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        err_console.print(f"[bold red]Error reading dbt schema:[/bold red] {exc}")
        raise typer.Exit(1)

    if not tables_list:
        console.print("[yellow]⚠  No models found in dbt project.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found [yellow]{len(tables_list)}[/yellow] dbt model(s).")

    if verbose:
        _print_schema_summary(tables_list)

    if dry_run:
        _print_dry_run_plan(tables_list, rows, format.value, str(output))
        raise typer.Exit(0)

    try:
        cfg = load_config(str(config) if config else None)
    except Exception as exc:
        err_console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(1)

    engine = ForgeEngine(
        tables=tables_list,
        rows=rows,
        seed=seed,
        config=cfg,
        output_dir=str(output),
        output_format=format.value,
    )
    try:
        results = engine.run()
    except Exception as exc:
        err_console.print(f"[bold red]Generation error:[/bold red] {exc}")
        raise typer.Exit(1)

    result_table = Table(
        "Model",
        "Rows",
        "Columns",
        "File",
        box=box.ROUNDED,
        border_style="green",
        title="[bold green]Generated dbt Model Data",
    )
    for tname, df in results.items():
        result_table.add_row(
            f"[cyan]{tname}[/cyan]",
            f"[yellow]{len(df):,}[/yellow]",
            str(df.width),
            f"[dim]{output}/{tname}.{format.value}[/dim]",
        )
    console.print(result_table)


# ===========================================================================
# version
# ===========================================================================


@app.command()
def version() -> None:
    """Print forge-mock version."""
    from forge_mock import __version__

    console.print(f"[bold cyan]forge-mock[/bold cyan] [yellow]{__version__}[/yellow]")


# ===========================================================================
# Helpers
# ===========================================================================


def _print_dry_run_plan(
    tables: list[TableSchema],
    rows: int,
    fmt: str,
    output_dir: str,
) -> None:
    plan = Table(
        "Table",
        "Columns",
        "Rows",
        "PKs",
        "FKs",
        "Output file",
        box=box.ROUNDED,
        border_style="yellow",
        title="[bold yellow]Dry Run — Generation Plan (nothing written)",
    )
    total_rows = 0
    for table in tables:
        plan.add_row(
            f"[cyan]{table.name}[/cyan]",
            str(len(table.columns)),
            f"[yellow]{rows:,}[/yellow]",
            str(len(table.primary_keys)),
            str(len(table.foreign_keys)),
            f"[dim]{output_dir}/{table.name}.{fmt}[/dim]",
        )
        total_rows += rows
    console.print(plan)
    console.print(
        f"\n[bold yellow]Dry run complete.[/bold yellow] "
        f"Would generate [yellow]{total_rows:,}[/yellow] total rows across "
        f"[cyan]{len(tables)}[/cyan] table(s). No files written."
    )


def _print_schema_summary(tables: list[TableSchema]) -> None:
    for table in tables:
        tbl = Table(
            "Column",
            "SQL Type",
            "Base Type",
            "PK",
            "Nullable",
            "FK",
            box=box.SIMPLE_HEAVY,
            title=f"[bold cyan]{table.name}[/bold cyan] [dim]({table.dialect})[/dim]",
            border_style="blue",
        )
        for col in table.columns:
            fk_label = ""
            if col.foreign_key:
                fk_label = (
                    f"→ {col.foreign_key.referenced_table}.{col.foreign_key.referenced_column}"
                )
            tbl.add_row(
                col.name,
                col.sql_type,
                col.base_type,
                "✓" if col.is_primary_key else "",
                "" if col.nullable else "NOT NULL",
                fk_label,
            )
        console.print(tbl)
        console.print()
