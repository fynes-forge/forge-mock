# ⚒️ Forge-Mock Roadmap

A strategic path from a DDL-based generator to a full-scale Synthetic Data Orchestrator.

---

## Phase 1: Foundation & Reliability — ✅ Complete (v0.2)

**Focus:** *Establishing trust through determinism and developer experience.*

- ✅ **Deterministic Seeding** — 100% bit-for-bit identical outputs across local and CI environments
- ✅ **DevOps Polish** — `CHANGELOG.md`, `CONTRIBUTING.md`, `pytest-cov`, `types-PyYAML` added to dev deps
- ✅ **`pyproject.toml` migration** — `[tool.uv]` dev-dependencies, hatchling build backend
- ✅ **`--dry-run`** — Preview generation plans to stdout without writing files
- ✅ **`--tables`** — Selective generation for named table subsets
- ✅ **`--verbose`** — High-fidelity row-level progress bars for massive schemas
- ✅ **Corrupt Mode Documentation** — Clear recipes for generating broken data
- ✅ **Code quality fixes** — removed `import pa` unused alias, fixed `dataclasses` import placement, fixed `utcnow()` deprecation

---

## Phase 2: Connectivity & Scoping — ✅ Complete (v0.4)

**Focus:** *Integration with existing infrastructure.*

- ✅ **SQLAlchemy Layer** — Connects to Postgres, MySQL, SQLite, Snowflake, BigQuery, Trino, DuckDB
- ✅ **Live Introspection** — Reads schemas directly from databases via SQLAlchemy `inspect()`
- ✅ **Connector extras** — `forge-mock[postgres]`, `[mysql]`, `[snowflake]`, `[bigquery]`, `[trino]`, `[duckdb]`, `[all-connectors]`
- ✅ **`forge-mock connect`** — Full connect → introspect → generate → insert pipeline
- ✅ **`forge-mock pull-schema`** — Exports live schema to a DDL file
- ✅ **`--insert-mode`** — `append | truncate | replace`
- ✅ **`--batch-size`** — Configurable INSERT batch size
- ✅ **`FORGE_DATABASE_URL`** env var — credentials never logged
- ✅ **`--include` / `--tables`** — Selective table targeting
- ✅ **Direct-to-DB** — Bulk insert via SQLAlchemy from Polars DataFrames

---

## Phase 3: The "Smart Plan" & PII Discovery — ✅ Complete (v0.6)

**Focus:** *Automating the "tedious" part of configuration.*

- ✅ **`generators/profiles.py`** — 45 named semantic profiles: NHS numbers, IBANs, CUSIPs, ISINs, LEIs, SSNs, sort codes, emails, postcodes, lat/lon, UUIDs, and more
- ✅ **`profiler/pii_detector.py`** — 30+ regex name rules + 10 value-pattern rules, returns `ProfileSuggestion` with confidence scores
- ✅ **`profiler/content_sampler.py`** — Samples 10–50 live rows per column to feed value-based detection
- ✅ **`forge-mock plan`** — Interactive wizard: analyses DB, prompts user per detection, writes `forge.yaml`
- ✅ **`--yes` flag** — Non-interactive auto-accept for CI
- ✅ **`profiler/forge_yaml_writer.py`** — Serialises confirmed plans to `forge.yaml` with metadata
- ✅ **Config extended** — `profile`, `source`, `locale`, `source_strategy` keys now supported

---

## Phase 4: External Data Sources & Composability — ✅ Complete (v0.7)

**Focus:** *Solving the "Niche Data" problem (SNOMED, CUSIP, Product Catalogs).*

- ✅ **`sources/reference_source.py`** — `ReferenceSource` (CSV/Parquet) and `SQLReferenceSource` with random/weighted/sequential strategies
- ✅ **`sources/seed_expander.py`** — Mutates golden records with per-column preserve/mutate/regenerate strategies; uses PII detection for type-aware regeneration
- ✅ **Multi-Locale Support** — `locale:` key at table or global level; per-table Faker instances
- ✅ **`--locale` flag** — CLI-level locale override (e.g. `en_GB`, `fr_FR`, `ja_JP`)
- ✅ **ForgeEngine wired** — reference sources, locale-aware Fakers, profile/source config overrides, row-level progress for large tables

Config usage:
```yaml
tables:
  diagnoses:
    locale: en_GB
    columns:
      snomed_code:
        source: data/snomed_subset.csv
        source_column: code
        source_strategy: random
      nhs_number:
        profile: nhs_number
```

---

## Phase 5: Validation & Ecosystem — ✅ Complete (v0.8)

**Focus:** *Ensuring data integrity and integrating with the modern data stack.*

- ✅ **`coherency/coherency_pass.py`** — Post-generation pass ensuring:
  - Temporal ordering (shipped_date ≥ order_date, end_date ≥ start_date)
  - Discount ≤ price
  - date_of_birth is ≥ 18 years in the past
- ✅ **`--coherent` flag** — Opt-in coherency enforcement
- ✅ **`coherency/schema_drift.py`** — Compares `forge.yaml` against a live database; reports added/removed tables and columns with severity levels
- ✅ **`forge-mock diff`** — CLI command for drift detection; `--strict` flag for CI gates
- ✅ **`coherency/dbt_reader.py`** — Parses `schema.yml`; extracts `accepted_values` → choice distributions, `relationships` → FK definitions, `not_null` → nullable=false, column descriptions → PII profile suggestions
- ✅ **`forge-mock dbt`** — Generate synthetic data directly from a dbt project
- ✅ **Docker test matrix** — `docker/docker-compose.yml` with Postgres 16, MySQL 8, Trino, BigQuery emulator
- ✅ **Integration tests** — Full round-trip tests for all engines in `tests/integration/`
- ✅ **`integration.yml`** GitHub Actions workflow — engine-per-job, service containers

---

## Version Summary

| Version | Phase | Status |
|---|---|---|
| v0.1 | — | DDL-first generator, file output |
| v0.2 | Phase 1 | Polish, dry-run, --tables filter, code fixes |
| v0.4 | Phase 2 | Live DB connectivity, pull-schema, direct insert |
| v0.6 | Phase 3 | PII detection, 45 semantic profiles, plan wizard |
| v0.7 | Phase 4 | Reference sources, seed expander, multi-locale |
| v0.8 | Phase 5 | Coherency pass, schema drift, dbt integration |
| v1.0 | — | GA release, full documentation site |

---

## Future Considerations

- **Great Expectations / Soda integration** — generate data guaranteed to pass an expectation suite
- **Terraform / Pulumi provider** — provision synthetic data as part of infrastructure bring-up
- **Web UI** — browser-based plan editor for non-CLI users
- **Streaming output** — write directly to Kafka topics or object storage (S3/GCS)
