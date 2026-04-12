"""dbt integration — reads schema.yml to drive forge-mock generation.

Extracts:
  - Model descriptions (to select Faker providers via PII detection)
  - accepted_values tests → drives `choice` distributions
  - relationships tests → FK definitions (bypasses DDL parsing)
  - not_null tests → sets nullable: false
  - Column descriptions → fed into PII detector for profile suggestions

Usage:
    forge-mock dbt --project-dir ./my_dbt_project --target dev --rows 500
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml  # type: ignore[import-untyped]

from forge_mock.parser.schema_models import ColumnSchema, ForeignKeySchema, TableSchema


class DbtReader:
    """Parses a dbt project's schema.yml files and produces TableSchema objects."""

    def __init__(self, project_dir: str) -> None:
        self._project_dir = Path(project_dir)

    def read(
        self,
        target: str = "dev",
        include_models: list[str] | None = None,
    ) -> list[TableSchema]:
        """Parse all schema.yml files in the project and return TableSchema objects."""
        schema_files = (
            list(self._project_dir.rglob("schema.yml"))
            + list(self._project_dir.rglob("_schema.yml"))
            + list(self._project_dir.rglob("models.yml"))
        )

        if not schema_files:
            raise FileNotFoundError(
                f"No schema.yml files found in {self._project_dir}. "
                "Make sure --project-dir points to a dbt project root."
            )

        tables: list[TableSchema] = []
        seen: set[str] = set()

        for schema_file in schema_files:
            for table in self._parse_schema_file(schema_file):
                if table.name in seen:
                    continue
                if include_models and table.name not in include_models:
                    continue
                seen.add(table.name)
                tables.append(table)

        return tables

    def _parse_schema_file(self, path: Path) -> list[TableSchema]:
        with path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        tables: list[TableSchema] = []

        # dbt schema.yml can have `models:` or `sources:` sections
        for section_key in ("models", "sources"):
            section = raw.get(section_key, [])
            # sources have a nested `tables:` key
            if section_key == "sources":
                section = [t for src in section for t in src.get("tables", [])]
            for model in section:
                table = self._parse_model(model)
                if table:
                    tables.append(table)

        return tables

    def _parse_model(self, model: dict[str, Any]) -> TableSchema | None:
        name = model.get("name")
        if not name:
            return None

        columns: list[ColumnSchema] = []
        for col_def in model.get("columns", []):
            col = self._parse_column(col_def)
            if col:
                columns.append(col)

        if not columns:
            # Model exists but no columns defined — create a minimal placeholder
            return TableSchema(name=name, dialect="dbt", columns=[])

        return TableSchema(name=name, dialect="dbt", columns=columns)

    def _parse_column(self, col_def: dict[str, Any]) -> ColumnSchema | None:
        name = col_def.get("name")
        if not name:
            return None

        nullable = True
        fk: ForeignKeySchema | None = None
        distribution: str | None = None
        dist_params: dict[str, Any] = {}
        profile: str | None = None

        # Parse dbt tests
        for test in col_def.get("tests", []):
            if test == "not_null":
                nullable = False
            elif test == "unique":
                pass  # handled by is_unique below
            elif isinstance(test, dict):
                # accepted_values → choice distribution
                if "accepted_values" in test:
                    values = test["accepted_values"].get("values", [])
                    if values:
                        distribution = "choice"
                        dist_params = {"values": values}

                # relationships → FK
                elif "relationships" in test:
                    rel = test["relationships"]
                    ref_model = rel.get("to", "").replace("ref('", "").replace("')", "")
                    ref_col = rel.get("field", name)
                    if ref_model:
                        fk = ForeignKeySchema(
                            column=name,
                            referenced_table=ref_model,
                            referenced_column=ref_col,
                        )

        # Use column description to suggest a profile via PII detection
        description = col_def.get("description", "")
        if not profile:
            from forge_mock.profiler.pii_detector import PIIDetector

            detector = PIIDetector()
            # Try name first, then description
            suggestion = detector.suggest(name) or (
                detector.suggest(description) if description else None
            )
            if suggestion and suggestion.confidence >= 0.80:
                profile = suggestion.profile

        is_pk = any(
            t == "primary_key" or (isinstance(t, dict) and "primary_key" in t)
            for t in col_def.get("tests", [])
        )
        is_unique = any(t == "unique" for t in col_def.get("tests", []))

        # dbt doesn't carry SQL types — we use VARCHAR as default
        # and rely on profiles / distributions for real generation
        sql_type = col_def.get("data_type", "VARCHAR")

        return ColumnSchema(
            name=name,
            sql_type=sql_type,
            base_type="VARCHAR",
            nullable=nullable,
            is_primary_key=is_pk,
            is_unique=is_unique,
            foreign_key=fk,
            distribution=distribution,
            dist_params=dist_params,
            profile=profile,
        )
