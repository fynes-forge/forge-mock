# forge-mock

> **Statistically realistic synthetic data from SQL DDL files.**

`forge-mock` is a high-performance Python CLI that reads your `CREATE TABLE` statements and produces synthetic datasets that respect your schema — column types, foreign keys, nullability, and statistical distributions — without ever touching production data.

---

<div align="center">

![Status](https://img.shields.io/badge/status-active-63C5EA?style=flat-square&labelColor=404E5C)
![License](https://img.shields.io/badge/license-MIT-9F7EBE?style=flat-square&labelColor=404E5C)
![Org](https://img.shields.io/badge/org-fynes--forge-ECDA90?style=flat-square&labelColor=404E5C)
[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![CI Status](https://github.com/username/repo-name/actions/workflows/ci.yml/badge.svg)](https://github.com/username/repo-name/actions)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

## Overview

Real data is messy, private, and hard to move. Test data is usually either too fake to be useful or too real to be safe. **Forge bridges that gap.**

- **Schema-first** — your DDL is the single source of truth
- **Referentially honest** — FK constraints are respected, not ignored
- **Statistically tunable** — override any column with a real distribution
- **Deterministic** — pin a `--seed` and get the same data every time
- **Battle-hardened** — inject corruption to test pipeline resilience

This is a Fynes Forge project built with **precision over cleverness**.

---

## Installation

```bash
pip install forge-mock
```

Or from source:

```bash
git clone https://github.com/your-org/forge-mock
cd forge-mock
pip install -e ".[dev]"
```

**Requirements:** Python 3.10+


---

---

## Quick Start

### 1. Point Forge at your DDL

```bash
forge generate schema.sql
```

This generates `1000` rows per table as `.parquet` files in the current directory.

### 2. Customise the run

```bash
forge generate schema.sql \
  --rows 5000 \
  --format csv \
  --dialect snowflake \
  --output ./data/synthetic \
  --seed 42
```

### 3. Inspect without generating

```bash
forge inspect schema.sql --dialect postgres
```

Prints a rich table of every column, its type mapping, PK/FK relationships, and nullability — no data written.

---

## Statistical Profiles (YAML Config)

Override any column with a specific distribution via a YAML file:

```yaml
# config.yaml
tables:
  orders:
    rows: 10000
    columns:
      total_amount:
        distribution: lognormal
        mean: 4.2
        sigma: 0.9
      status:
        distribution: choice
        values: [pending, shipped, delivered, cancelled]
  products:
    rows: 500
    columns:
      price:
        distribution: normal
        mean: 49.99
        std: 15.0
      stock_qty:
        distribution: poisson
        lam: 75
```

Run with:

```bash
forge generate schema.sql --config config.yaml
```

### Supported Distributions

| Distribution | Parameters |
|---|---|
| `normal` | `mean`, `std`, `decimals` |
| `uniform` | `low`, `high`, `decimals` |
| `lognormal` | `mean`, `sigma`, `decimals` |
| `poisson` | `lam` |
| `exponential` | `scale`, `decimals` |
| `binomial` | `n`, `p` |
| `beta` | `a`, `b`, `decimals` |
| `gamma` | `shape`, `scale`, `decimals` |
| `choice` | `values` (list) |
| `integer_range` | `low`, `high` |

---

## Schema Drift / Corruption Mode

Test your pipeline's resilience against bad data:

```bash
forge generate schema.sql --corrupt 0.05
```

`--corrupt 0.05` injects bad values into ~5% of cells: nulls in non-nullable columns, type mismatches, out-of-range integers, invalid dates, empty strings, and control characters.

---

## CLI Reference

```
Usage: forge [COMMAND] [OPTIONS]

Commands:
  generate   Generate synthetic data from a DDL file
  inspect    Inspect a DDL file schema without generating data
  version    Print forge-mock version

forge generate OPTIONS:
  DDL                     Path to SQL DDL file          [required]
  --rows, -r INT          Rows per table                [default: 1000]
  --output, -o PATH       Output directory              [default: .]
  --format, -f            Output format                 [parquet|csv|sql]
  --dialect, -d           SQL dialect                   [postgres|snowflake|bigquery|trino|...]
  --seed, -s INT          Random seed for reproducibility
  --config, -c PATH       YAML config for distribution overrides
  --corrupt FLOAT         Corruption injection rate (0.0–1.0)
  --verbose, -v           Show detailed schema info
```

---

## Supported SQL Dialects

| Dialect | Status |
|---|---|
| `postgres` | ✅ Full support |
| `snowflake` | ✅ Full support |
| `bigquery` | ✅ Full support |
| `trino` | ✅ Full support |
| `duckdb` | ✅ Full support |
| `mysql` | ✅ Full support |
| `sqlite` | ✅ Full support |

---

## Output Formats

| Format | Description |
|---|---|
| `parquet` | Snappy-compressed via PyArrow — best for analytics pipelines |
| `csv` | UTF-8, comma-delimited — universal compatibility |
| `sql` | Batched `INSERT INTO` statements — ready to replay |

---

## Project Structure

```
forge-mock/
├── src/
│   └── forge_mock/
│       ├── __init__.py
│       ├── cli/
│       │   └── main.py          # Typer CLI entry point
│       ├── parser/
│       │   ├── ddl_parser.py    # sqlglot-based DDL parser
│       │   └── schema_models.py # ColumnSchema, TableSchema dataclasses
│       ├── generators/
│       │   ├── column_generator.py      # Per-column value generation
│       │   ├── distribution_generator.py # NumPy statistical distributions
│       │   └── type_map.py              # SQL type → Faker provider mapping
│       └── engine/
│           ├── forge_engine.py     # Orchestration & serialisation
│           ├── dependency_graph.py # FK dependency resolution (networkx DAG)
│           └── config_loader.py    # YAML config loader
├── tests/
│   ├── conftest.py
│   ├── fixtures.py
│   ├── test_parser.py
│   └── test_engine.py
├── examples/
│   ├── ecommerce.sql
│   └── ecommerce_config.yaml
└── pyproject.toml
```

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage report
pytest --cov=forge_mock --cov-report=html

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

---

## CI/CD Integration

Pin a seed for byte-for-byte reproducible test fixtures:

```bash
# Generate fixed test data as part of your CI pipeline
forge generate tests/schema.sql \
  --rows 100 \
  --seed 42 \
  --format parquet \
  --output tests/fixtures/
```

---

## Example: Full E-Commerce Run

```bash
forge generate examples/ecommerce.sql \
  --config examples/ecommerce_config.yaml \
  --format parquet \
  --output ./data \
  --seed 42 \
  --verbose
```

Expected output:

```
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  ...

┌─ Run Configuration ──────────────────────┐
│ DDL File    ecommerce.sql                 │
│ Rows/table  1000                          │
│ Format      parquet                       │
│ Seed        42                            │
└───────────────────────────────────────────┘

▶ customers  → 500 rows
▶ categories → 20 rows
▶ products   → 200 rows
▶ orders     → 2,000 rows
▶ order_items→ 5,000 rows

✓ Done. Generated 5 table(s) in ./data

╭─ Generated Datasets ──────────────────────────────────────╮
│ Table        │ Rows  │ Columns │ File                      │
│ customers    │ 500   │ 7       │ ./data/customers.parquet  │
│ categories   │ 20    │ 3       │ ./data/categories.parquet │
│ products     │ 200   │ 8       │ ./data/products.parquet   │
│ orders       │ 2,000 │ 7       │ ./data/orders.parquet     │
│ order_items  │ 5,000 │ 5       │ ./data/order_items.parquet│
╰───────────────────────────────────────────────────────────╯
```

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.

---

## Licence

MIT © [Fynes Forge](https://github.com/fynes-forge) — see [LICENSE](./LICENSE) for details.
