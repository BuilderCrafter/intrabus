# Contributing to intrabus

Thanks for considering a contribution to **intrabus**.

`intrabus` is a small Python communication library. The project goal is to stay simple, embeddable, and easy to use while providing useful runtime observability.

## Development setup

Install `uv` if you do not already have it, then run:

```bash
uv sync --dev
```

Run the test suite:

```bash
uv run pytest -q
```

Run linting:

```bash
uv run ruff check .
```

Run formatting checks:

```bash
uv run ruff format --check .
```

Format the code:

```bash
uv run ruff format .
```

## Pull request checklist

Before opening a pull request, please make sure:

- tests pass
- Ruff checks pass
- public APIs are documented if changed
- new behavior has tests
- examples are updated when user-facing behavior changes
- the README is updated for major changes

## Design principles

Please keep these principles in mind:

1. Keep the library general-purpose.
2. Keep the default setup simple.
3. Prefer `CommunicationNode` as the high-level user entry point.
4. Keep lower-level components reusable.
5. Avoid unbounded memory usage.
6. Keep monitoring/dashboard/demo code outside this package.
7. Avoid adding external infrastructure dependencies.
8. Prepare for future multi-node support without forcing it into the current API.

## Release process

For maintainers, the usual release flow is:

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
rm -rf dist build *.egg-info
uv run python -m build
uv run twine check dist/*
```

Then tag and push:

```bash
git tag v0.2.2
git push origin main
git push origin v0.2.2
```

The publishing workflow should publish tagged releases to PyPI.
