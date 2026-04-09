# Contributing to Fynes Forge Projects

Thank you for your interest in contributing. This guide covers everything you need to know to open a high-quality pull request.

---

## Code of Conduct

Be respectful, constructive, and direct. Fynes Forge projects follow a simple standard: treat contributors the way you'd want to be treated on a professional engineering team.

---

## How to Contribute

### Reporting a Bug

1. Search [existing issues](../../issues) to avoid duplicates
2. Open a new issue using the **Bug Report** template
3. Include: what you expected, what happened, steps to reproduce, and your environment

### Suggesting a Feature

1. Open an issue using the **Feature Request** template
2. Describe the problem you're solving, not just the solution
3. Wait for a maintainer to approve the direction before opening a PR

### Submitting a Pull Request

1. Fork the repository and create a branch from `main`
2. Name your branch descriptively: `fix/broken-pipeline-config` or `feat/add-dbt-support`
3. Make your changes — keep commits small and focused
4. Ensure all checks pass locally before pushing (see below)
5. Open a PR using the provided template
6. A maintainer will review within a reasonable timeframe

---

## Branch Naming

| Type | Pattern | Example |
|---|---|---|
| Feature | `feat/<description>` | `feat/add-snowflake-connector` |
| Bug fix | `fix/<description>` | `fix/null-handling-in-transform` |
| Documentation | `docs/<description>` | `docs/update-getting-started` |
| Chore | `chore/<description>` | `chore/bump-dependencies` |
| Release | `release/<version>` | `release/1.2.0` |

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**

```
feat(pipeline): add incremental load support for Snowflake
fix(transform): handle null values in date columns
docs(readme): update installation steps for Python 3.12
chore(deps): bump ruff to 0.4.0
```

---

## Code Standards

All contributions must pass the following checks before a PR can be merged:

```bash
ruff check .          # Linting
ruff format .         # Formatting
mypy src/             # Type checking
pytest                # Tests
```

These run automatically in CI. A failing check blocks merge.

**Key principles:**

- Type-hint all function signatures
- Write docstrings for public functions and classes
- Keep functions small and single-purpose
- Prefer explicit over clever — code is read far more than it is written
- Tests are required for new features; a PR without tests will not be merged

---

## Pull Request Standards

- PRs should be small and focused — one logical change per PR
- Reference the issue your PR closes: `Closes #42`
- Fill in the PR template completely — empty sections will prompt a request for changes
- Screenshots or output logs are appreciated for non-trivial changes

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- `MAJOR` — breaking changes
- `MINOR` — new backwards-compatible features
- `PATCH` — bug fixes

Changes are documented in [CHANGELOG.md](./CHANGELOG.md).

---

## Licence

By contributing, you agree that your contributions will be licensed under the same [MIT Licence](./LICENSE) as the project.
