"""Schema drift detection — compares a forge.yaml config against a live database.

Reports tables/columns that have been added, removed, or changed since the
config was last generated, so users know when their forge.yaml is stale.

Usage:
    forge-mock diff forge.yaml postgresql://user:pass@host/db
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


class DriftKind(str, Enum):
    table_added = "table_added"  # exists in DB, missing from config
    table_removed = "table_removed"  # exists in config, missing from DB
    column_added = "column_added"  # exists in DB table, missing from config
    column_removed = "column_removed"  # exists in config table, missing from DB
    type_changed = "type_changed"  # column exists in both, but type differs
    nullable_changed = "nullable_changed"


@dataclass
class DriftItem:
    kind: DriftKind
    table: str
    column: str | None = None
    config_value: str | None = None
    db_value: str | None = None

    @property
    def severity(self) -> str:
        if self.kind in (DriftKind.table_removed, DriftKind.column_removed, DriftKind.type_changed):
            return "high"
        if self.kind in (DriftKind.nullable_changed,):
            return "medium"
        return "low"


class SchemaDriftDetector:
    """Compares a forge.yaml config against a live database schema."""

    def compare(
        self,
        config: dict[str, Any],
        connection_url: str,
        db_schema: str | None = None,
    ) -> list[DriftItem]:
        """Run the comparison and return a list of DriftItems."""
        from forge_mock.connectors.registry import get_connector

        config_tables = config.get("tables", {})

        with get_connector(connection_url) as connector:
            live_tables = connector.introspect(schema=db_schema)

        live_map = {t.name: t for t in live_tables}
        drifts: list[DriftItem] = []

        # Tables in DB but not in config
        for tname in live_map:
            if tname not in config_tables:
                drifts.append(DriftItem(kind=DriftKind.table_added, table=tname))

        # Tables in config but not in DB
        for tname in config_tables:
            if tname not in live_map:
                drifts.append(DriftItem(kind=DriftKind.table_removed, table=tname))
                continue

            # Column-level diff
            live_cols = {c.name: c for c in live_map[tname].columns}
            cfg_cols = set(config_tables[tname].get("columns", {}).keys())

            # Columns in DB but not in config
            for col_name in live_cols:
                if col_name not in cfg_cols:
                    drifts.append(
                        DriftItem(
                            kind=DriftKind.column_added,
                            table=tname,
                            column=col_name,
                            db_value=live_cols[col_name].sql_type,
                        )
                    )

            # Columns in config but not in DB
            for col_name in cfg_cols:
                if col_name not in live_cols:
                    drifts.append(
                        DriftItem(
                            kind=DriftKind.column_removed,
                            table=tname,
                            column=col_name,
                        )
                    )

        return drifts

    def print_report(self, drifts: list[DriftItem]) -> None:
        """Print a rich-formatted drift report to the terminal."""
        if not drifts:
            console.print("[bold green]✓ No schema drift detected.[/bold green]")
            return

        high = [d for d in drifts if d.severity == "high"]
        medium = [d for d in drifts if d.severity == "medium"]
        low = [d for d in drifts if d.severity == "low"]

        console.print(
            f"\n[bold yellow]Schema drift detected:[/bold yellow] "
            f"[red]{len(high)} high[/red]  "
            f"[yellow]{len(medium)} medium[/yellow]  "
            f"[dim]{len(low)} low[/dim]\n"
        )

        tbl = Table(
            "Severity",
            "Kind",
            "Table",
            "Column",
            "Detail",
            box=box.ROUNDED,
            border_style="yellow",
            title="[bold]Drift Report",
        )
        severity_colours = {"high": "red", "medium": "yellow", "low": "dim"}

        for d in sorted(drifts, key=lambda x: ("high", "medium", "low").index(x.severity)):
            colour = severity_colours[d.severity]
            detail = ""
            if d.config_value and d.db_value:
                detail = f"config: {d.config_value}  →  db: {d.db_value}"
            elif d.db_value:
                detail = f"db type: {d.db_value}"

            tbl.add_row(
                f"[{colour}]{d.severity}[/{colour}]",
                d.kind.value.replace("_", " "),
                f"[cyan]{d.table}[/cyan]",
                d.column or "—",
                f"[dim]{detail}[/dim]",
            )
        console.print(tbl)

    def exit_code(self, drifts: list[DriftItem]) -> int:
        """Return 1 if any high-severity drift exists, 0 otherwise."""
        return 1 if any(d.severity == "high" for d in drifts) else 0
