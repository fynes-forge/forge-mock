# Getting Started

> A complete guide to setting up and running this project locally.

---

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.11+ | Recommended: use `pyenv` to manage versions |
| pip | 23.0+ | Comes with Python |
| Git | 2.40+ | |
| Docker | 24.0+ | Optional — for containerised runs |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/fynes-forge/<repo-name>.git
cd <repo-name>
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
.venv\Scripts\activate          # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

For development dependencies (linting, testing, formatting):

```bash
pip install -r requirements-dev.txt
```

### 4. Configure environment variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and update the required values — each variable is documented inline.

---

## Running the Project

### Local run

```bash
python src/main.py
```

### With Docker

```bash
docker build -t fynes-forge/<repo-name> .
docker run --env-file .env fynes-forge/<repo-name>
```

---

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_main.py -v
```

---

## Code Quality

This project uses the following tools — all configured in `pyproject.toml`:

| Tool | Purpose | Run |
|---|---|---|
| `ruff` | Linting + formatting | `ruff check . && ruff format .` |
| `mypy` | Type checking | `mypy src/` |
| `pytest` | Testing | `pytest` |

Run all checks at once:

```bash
ruff check . && ruff format . && mypy src/ && pytest
```

These same checks run automatically in CI on every push and pull request.

---

## Data Pipeline Projects

If this repo is a data pipeline, additional setup may be required:

```bash
# Airflow (if applicable)
export AIRFLOW_HOME=$(pwd)/airflow
airflow db init
airflow standalone

# dbt (if applicable)
dbt deps
dbt debug
dbt run
```

Refer to `docs/pipeline.md` if present for pipeline-specific documentation.

---

## IDE Setup

### VS Code

Recommended extensions are defined in `.vscode/extensions.json`. VS Code will prompt you to install them on first open.

Settings are pre-configured in `.vscode/settings.json` to use `ruff` for linting and formatting on save.

---

## Troubleshooting

**`ModuleNotFoundError` on run**
Ensure your virtual environment is activated: `source .venv/bin/activate`

**Environment variables not loading**
Ensure `.env` exists and is populated. Never commit `.env` — it is in `.gitignore`.

**CI failing locally but not expected to**
Run `ruff check . && mypy src/ && pytest` locally to replicate the CI checks before pushing.

---

## Getting Help

- Open a [GitHub Issue](../../issues) for bugs or questions
- See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to propose changes
