# Release checklist

Use this checklist before publishing a new intrabus release.

## 1. Update version and docs

- Update `pyproject.toml` version.
- Update `CHANGELOG.md`.
- Update `README.md` if behavior changed.
- Update examples if the recommended API changed.

## 2. Clean generated files

```bash
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .ruff_cache build dist *.egg-info
```

## 3. Run checks

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## 4. Build distributions

```bash
rm -rf dist build *.egg-info
uv run python -m build
uv run twine check dist/*
```

## 5. Test install locally

```bash
python -m venv .venv-install-test
source .venv-install-test/bin/activate  # Windows: .venv-install-test\Scripts\activate
pip install dist/*.whl
python -c "from intrabus import CommunicationNode, BusInterface; print('ok')"
deactivate
```

## 6. Publish

Recommended: publish from GitHub Actions using PyPI Trusted Publishing.

```bash
git add .
git commit -m "Prepare intrabus 0.2.3 release"
git tag v0.2.3
git push origin main
git push origin v0.2.3
```

## 7. Verify

After publishing:

```bash
python -m venv .venv-pypi-test
source .venv-pypi-test/bin/activate  # Windows: .venv-pypi-test\Scripts\activate
pip install intrabus==0.2.3
python -c "from intrabus import CommunicationNode, BusInterface; print('ok')"
deactivate
```
