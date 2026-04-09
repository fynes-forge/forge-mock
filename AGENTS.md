# AGENTS.md

> Context and conventions for AI coding agents (Copilot, Claude, Cursor, etc.) working in this repository.

---

## Organisation Context

This repository belongs to **Fynes Forge** — the open source engineering organisation of Tom Fynes, Senior Data Engineer.

- **GitHub:** https://github.com/fynes-forge
- **Portfolio:** https://fynes-forge.github.io
- **Primary focus:** Data engineering, Python tooling, documentation

---

## Project Purpose

<!-- Replace this section when using the template -->
Describe what this specific repo does in 2–3 sentences. Agents use this to understand the domain and make better suggestions.

---

## Technology Stack

### Primary

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Linting / formatting | Ruff |
| Type checking | mypy |
| Testing | pytest |
| Package management | pip + `pyproject.toml` |

### Data (if applicable)

| Tool | Purpose |
|---|---|
| Apache Airflow | Orchestration |
| dbt | Transformation |
| Snowflake / Trino | Warehousing / query engine |
| Apache Spark | Large-scale processing |

---

## Code Conventions

Agents should follow these conventions without being asked:

### Python

- **Type hints are required** on all function signatures — no `Any` unless genuinely unavoidable
- **Docstrings** on all public functions and classes — Google style
- **Ruff** is the formatter and linter — do not suggest Black, Flake8, or isort
- **No wildcard imports** — `from module import *` is never acceptable
- **Prefer `pathlib.Path`** over `os.path` for file operations
- **Prefer `dataclasses` or `pydantic`** over plain dicts for structured data
- Functions should do one thing. If a function needs a long docstring to explain what it does, it should be split.

### General

- **Conventional Commits** for all commit messages — `feat:`, `fix:`, `docs:`, `chore:` etc.
- **No commented-out code** in PRs — delete it or put it behind a feature flag
- **No print statements** in production code — use the `logging` module
- **Environment variables** via `.env` + `python-dotenv` — never hardcode secrets

---

## Branch & PR Conventions

- Default branch: `main`
- Branch naming: `feat/<description>`, `fix/<description>`, `docs/<description>`, `chore/<description>`
- PRs require: passing CI, filled-in PR template, reference to an issue where applicable

---

## What Agents Should Avoid

- ❌ Suggesting framework migrations or major dependency changes without being asked
- ❌ Rewriting working code into a different style without a clear reason
- ❌ Adding comments that restate what the code already clearly shows
- ❌ Using `try/except Exception` as a catch-all without re-raising or specific handling
- ❌ Generating placeholder TODO comments and leaving them in — complete the implementation or flag it explicitly
- ❌ Ignoring type hints in generated code

---

## Testing Standards

- Tests live in `tests/` mirroring the `src/` structure
- Test file naming: `test_<module_name>.py`
- Use `pytest` fixtures — avoid repetitive setup in test functions
- Aim for meaningful coverage of business logic — not 100% line coverage for its own sake
- Data pipeline tests should use small, committed fixture datasets in `tests/fixtures/`

---

## File Structure Reference

```
src/
├── __init__.py
├── main.py          ← Entry point
├── config.py        ← Config loading (env vars, settings)
├── models/          ← Data models / schemas
├── pipeline/        ← Pipeline logic (if data project)
├── utils/           ← Shared utilities
└── ...

tests/
├── conftest.py      ← Shared fixtures
├── fixtures/        ← Test data
└── test_*.py        ← Test modules
```

---

## Security

- Never suggest committing secrets, API keys, tokens, or passwords
- All credentials must use environment variables
- Dependency suggestions should be from well-maintained, widely-used packages
- Flag any use of `eval()`, `exec()`, `subprocess` with shell=True, or `pickle` — these require explicit review
