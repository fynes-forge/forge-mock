"""Pydantic-style dataclasses for representing parsed SQL schema objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ForeignKeySchema:
    """Represents a foreign key constraint on a column."""

    column: str
    referenced_table: str
    referenced_column: str


@dataclass
class ColumnSchema:
    """Represents a single column in a SQL table."""

    name: str
    sql_type: str  # Raw SQL type string, e.g. "VARCHAR(255)"
    base_type: str  # Normalised base type, e.g. "VARCHAR"
    type_params: list[int] = field(default_factory=list)
    nullable: bool = True
    is_primary_key: bool = False
    is_unique: bool = False
    default: Optional[str] = None
    foreign_key: Optional[ForeignKeySchema] = None
    # Statistical distribution override (populated from YAML config)
    distribution: Optional[str] = None
    dist_params: dict[str, float] = field(default_factory=dict)
    # Semantic profile override — Phase 3 (e.g. "email", "nhs_number", "iban")
    profile: Optional[str] = None
    # Reference data source — Phase 4
    source: Optional[str] = None  # path or key to a ReferenceSource
    source_column: Optional[str] = None  # which column to draw from the source
    source_strategy: str = "random"  # random | weighted | sequential
    # Locale hint for coherent-mode generation — Phase 5
    locale: Optional[str] = None


@dataclass
class TableSchema:
    """Represents a complete SQL table definition."""

    name: str
    dialect: str
    columns: list[ColumnSchema] = field(default_factory=list)
    # Locale applied to this whole table in coherent mode
    locale: Optional[str] = None

    @property
    def primary_keys(self) -> list[str]:
        return [c.name for c in self.columns if c.is_primary_key]

    @property
    def foreign_keys(self) -> list[ForeignKeySchema]:
        return [c.foreign_key for c in self.columns if c.foreign_key is not None]

    @property
    def dependencies(self) -> list[str]:
        """Return names of tables this table depends on (via FK)."""
        return list({fk.referenced_table for fk in self.foreign_keys})
