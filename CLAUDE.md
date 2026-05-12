# CLAUDE.md

This file provides guidance to Claude Code when working in the Charm SDK repo.

**Read [AGENTS.md](AGENTS.md) first.** That file is the cross-agent source of
truth for repo boundaries, commands, release rules, and placement decisions.

This repository contains the public `charmos` Python package, the `charm` CLI,
runtime templates, execution backends, and docs source.

## Start Here

- Read `pyproject.toml` before changing package metadata, dependencies, entry points, or release behavior.
- Read `.github/workflows/ci.yml` before changing CI checks.
- Read `.github/workflows/publish-testpypi.yml` and `.github/workflows/publish-pypi.yml` before changing package publishing.
- Read `docs/oss/release-process.mdx` before changing release process docs.
- Read `docs/docs.json` before changing docs navigation.

## Repo Boundary

| Area | Purpose |
|------|---------|
| `src/charm/cli/` | CLI commands and local developer workflow |
| `src/charm/contracts/` | `charm.yaml` schema and validation |
| `src/charm/adapters/` | Adapter integration layer |
| `src/charm/runner/` | Runner protocol, script generation, skills, backend abstraction |
| `src/charm/templates/` | Built-in template manifests |
| `docs/` | Public documentation source |

Keep these boundaries clear. Do not duplicate the same behavior across CLI,
adapter, and runner layers.

## Release Hold

Do not publish Charm unless explicitly asked.

- Do not create or push `v*` tags.
- Do not publish to PyPI from a local machine.
- Do not trigger production PyPI publishing unless requested.
- Do not add PyPI token secrets; use Trusted Publishing.

## Development Commands

### Setup

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[runner,dev]"
```

### Lint

```bash
ruff check src
ruff check src --fix
```

### Type Check

```bash
mypy src/charm
```

### Tests

```bash
pytest
pytest tests/test_foo.py
pytest tests/test_foo.py::test_bar
```

### Package Validation

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

## Review Priorities

- Keep SDK, CLI, `charm.yaml`, and package behavior stable for existing users.
- Treat docs, package metadata, runtime images, and release workflows as public surfaces.
- Keep changelog labels and PR release notes accurate.
- Validate OpenAPI docs navigation through the referenced spec file.
- Never relax checks just to make CI green. Fix the underlying issue or document a narrow, justified exception.

## Don't

- Do not commit secrets, tokens, `.env` files, or service account keys.
- Do not add duplicate helpers with overlapping ownership.
- Do not hide third-party integration failures behind broad fallbacks.
- Do not create compatibility shims for unshipped branch-only behavior unless requested.
- Do not make package publishing depend on a maintainer's local machine.
