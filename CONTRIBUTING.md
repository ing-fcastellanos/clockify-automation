# Contributing

Thanks for taking the time to contribute. This document covers the basics of
getting a development environment up, the checks the project enforces, and how
releases are cut.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency and
environment management. With uv installed:

```
uv sync --extra dev
```

If you prefer plain pip:

```
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
.\.venv\Scripts\activate      # Windows PowerShell
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in the JIRA / Clockify credentials so
the integration tests and end-to-end runs can talk to real APIs when needed.

## Quality checks

Before pushing a PR, run all four checks. CI will run the same set on every
push and pull request.

```
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

If you have `pre-commit` installed, you can register the hook so the
formatting and basic-yaml checks run automatically on every commit:

```
uv run pre-commit install
```

## Pull requests

- Branch off `main`.
- Keep changes focused. One PR = one logical change.
- Update `CHANGELOG.md` under the `[Unreleased]` section if your change is
  user-visible (CLI flag, behaviour, dependency bump).
- New behaviour needs a test. Bug fixes should include a regression test.
- All four checks above must pass.

## Releases

Versions live in **one place**: `__version__` in
`src/clockify_automation/__init__.py`. `pyproject.toml` reads it dynamically
through `[tool.hatch.version]`.

To cut a release:

1. Bump `__version__` (Semantic Versioning).
2. Move entries from `## [Unreleased]` into a new section `## [X.Y.Z] - YYYY-MM-DD`
   in `CHANGELOG.md`. Update the comparison links at the bottom.
3. Open a PR, merge to `main`.
4. Tag the merge commit: `git tag vX.Y.Z && git push --tags`.
5. The `publish.yml` GitHub Action builds and uploads to PyPI on tag push, and
   creates a GitHub Release with the changelog notes.

## Reporting issues

Open a [GitHub issue](https://github.com/ing-fcastellanos/clockify-automation/issues)
with the command you ran, the JIRA / Clockify account types involved (Cloud,
self-hosted), and the relevant log output (run with `-v` for verbose logs).
Redact any tokens or credentials.
