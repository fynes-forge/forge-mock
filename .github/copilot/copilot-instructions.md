# GitHub Copilot Instructions

> These instructions apply to all Copilot interactions in this repository.

---

## Organisation & Project

You are assisting with a **Fynes Forge** project. Fynes Forge is the open source engineering organisation of Tom Fynes, a Senior Data Engineer. Projects focus on data engineering, Python tooling, and technical education.

Apply the conventions in `AGENTS.md` at all times unless explicitly overridden in a specific file or comment.

---

## Code Style

- Write **Python 3.11+** — use modern syntax (`match`, `|` union types, `tomllib`, etc.) where appropriate
- Always include **type hints** on function signatures
- Use **Google-style docstrings** for public functions and classes
- Format with **Ruff** conventions — 88 char line length, double quotes
- Prefer **explicit and readable** over clever and compact

### Good example

```python
def load_config(path: Path) -> dict[str, str]:
    """Load configuration from a TOML file.

    Args:
        path: Path to the TOML configuration file.

    Returns:
        Dictionary of configuration key-value pairs.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)
```

### Avoid

```python
# No type hints, no docstring, bare except
def load_config(path):
    try:
        return tomllib.load(open(path, "rb"))
    except:
        return {}
```

---

## Data Engineering Specifics

When working with data pipeline code:

- Prefer **incremental patterns** over full refreshes where possible
- Always handle **null / None values** explicitly — do not assume clean data
- Use **logging** to record row counts, durations, and errors at key pipeline stages
- SQL should be in **separate `.sql` files** or **dbt models**, not embedded as long strings in Python
- For Airflow DAGs: keep tasks small, use `@task` decorator style, avoid `BashOperator` unless necessary

---

## Testing

When generating or suggesting tests:

- Use `pytest` — not `unittest`
- Create fixtures in `conftest.py`
- Use small, realistic fixture data — not arbitrary random values
- Name tests descriptively: `test_load_config_raises_when_file_missing`
- Cover the happy path and at least one failure/edge case per function

---

## What Copilot Should Not Do

- Do not suggest `requirements.txt` changes without noting them explicitly
- Do not use deprecated libraries (e.g. `distutils`, `optparse`, `imp`)
- Do not generate `print()` statements for logging — use `logging.getLogger(__name__)`
- Do not leave `# TODO` comments in generated code — complete the implementation
- Do not use `os.path` — use `pathlib.Path`
- Do not suggest `pandas` for data that should stay in the warehouse — push computation down

---

## Commit Messages

Always suggest commit messages in Conventional Commits format:

```
feat(scope): short description in imperative mood

Optional longer body explaining why, not what.

Closes #<issue>
```
