# AGENTS.md

Repository-level guidance for AI coding agents (e.g., Claude, Cursor, Copilot) working in the Charm SDK repository.

This file serves as the definitive source of truth for architectural boundaries, development commands, and release rules. **All agents must read and adhere to these guidelines before executing changes.**

## Core Agent Instructions

- **Be Concise & Direct:** Prioritize technical accuracy. Do not apologize or use overly conversational filler.
- **Preserve Existing Code:** Maintain all existing comments, docstrings, and unchanged logic unless explicitly asked to modify them.
- **Respect Boundaries:** Follow the repository boundary rules strictly. Do not duplicate logic across CLI, adapter, and runner layers.

## Repo Boundary (Canonical Ownership)

This repository owns the public Python SDK, CLI, agent templates, runtime image definitions, and documentation source for Charm.

| Area | Owns |
|------|------|
| `src/charm/cli/` | `charm` CLI commands, local developer workflows, auth/config state |
| `src/charm/contracts/` | `charm.yaml` schema and validation models |
| `src/charm/adapters/` | Framework adapters for LangChain, LangGraph, CrewAI, OpenClaw, custom/process runtimes |
| `src/charm/runner/` | Runner protocol, script generation, skills, backend abstraction |
| `src/charm/runner/backend/` | Docker, Cloud Run, Fly.io, and related execution backends |
| `src/charm/templates/` | Built-in starter manifests and agent templates |
| `docs/` | Public docs source for docs.charmos.io |
| `docker/` | Runtime image build definitions (`Dockerfile.base`, `.langchain`, etc.) |

> **Warning:** Do not move behavior across these boundaries without updating imports, docs, tests, and release notes together.

## Production Status

This repo is production-facing because it publishes the `charmos` package and the public CLI. Preserve existing user-facing SDK, CLI, package, and `charm.yaml` behavior unless the task explicitly changes it.

When changing public behavior:

- Update docs.
- Update package/release notes.
- Add or update tests where practical.
- Describe migration or compatibility impact in the PR.

## Release Hold

**Do not publish from this repo unless the user explicitly requests a release.**

- Do not create or push `v*` tags unless asked.
- Do not trigger production PyPI publishing unless asked.
- Do not treat configured Trusted Publishers or GitHub environments as release approval.
- Do not upload wheels or source distributions from a local machine for official releases.
- Do not introduce long-lived PyPI API tokens when Trusted Publishing is available.

*Note: Normal code pushes and TestPyPI dry runs are fine when requested.*

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

### Package Build

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

### Runtime Images

```bash
docker build -f docker/Dockerfile.base -t charm-runner-base:ci .
docker build -f docker/Dockerfile.langchain -t charm-runner-langchain:ci .
```

## Docs Rules

- Keep `docs/docs.json` synchronized with actual `.mdx` files.
- OpenAPI groups in `docs/docs.json` validate the OpenAPI spec file, not generated operation pages.
- Avoid hidden `TODO` placeholders in public docs.
- Keep contributor-facing docs practical and explicit.
- Use lowercase kebab-case for new docs pages unless the file is a conventional root file such as `README.md`, `AGENTS.md`, or `CLAUDE.md`.

## Engineering Rules

- Prefer existing adapters, runner abstractions, and CLI patterns before adding new architecture.
- Replace duplicated behavior at the source instead of adding parallel helpers.
- Do not add compatibility shims for in-progress branch work unless the user asks.
- Do not commit secrets, `.env` files, credentials, local tokens, or service account keys.
- Do not relax lint, type, docs, or package checks just to make CI green.
- Keep release-facing PRs labeled with exactly one release category label such as `release:feature`, `release:fix`, `release:infra`, or `release:skip`.

## Decision Rules

When adding code, decide placement in this order:

1. **CLI or developer workflow?** -> `src/charm/cli/`
2. **`charm.yaml` or validation?** -> `src/charm/contracts/`
3. **Framework-specific execution glue?** -> `src/charm/adapters/`
4. **Runner orchestration, script generation, or protocol?** -> `src/charm/runner/`
5. **Backend-specific execution infrastructure?** -> `src/charm/runner/backend/`
6. **Starter-agent content?** -> `src/charm/templates/` (and update docs)
7. **Public usage guidance?** -> `docs/`

> **Key Principle:** A feature is not a CLI feature just because it can be triggered locally. If it changes runtime execution, keep the source of truth in the runner or adapter layer and let the CLI call into it.
