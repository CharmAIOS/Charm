# AGENTS.md

Repository-level guidance for coding agents working in the Charm SDK repo.

Read [CLAUDE.md](CLAUDE.md), [README.md](README.md), and
[docs/oss/release-process.mdx](docs/oss/release-process.mdx) before changing
release behavior.

This repo owns the public Python SDK, CLI, agent templates, runtime image
definitions, and documentation source for Charm.

## Repo Boundary

Canonical ownership:

| Area | Owns |
|------|------|
| `src/charm/cli/` | `charm` CLI commands, local developer workflows, auth/config state |
| `src/charm/contracts/` | `charm.yaml` schema and validation models |
| `src/charm/adapters/` | Framework adapters for LangChain, LangGraph, CrewAI, OpenClaw, custom/process runtimes |
| `src/charm/runner/` | Runner protocol, script generation, skills, backend abstraction |
| `src/charm/runner/backend/` | Docker, Cloud Run, Fly.io, and related execution backends |
| `src/charm/templates/` | Built-in starter manifests and agent templates |
| `docs/` | Public docs source for docs.charmos.io |
| `Dockerfile.standard` / `Dockerfile.full` | Runtime image build definitions |

Do not move behavior across these boundaries without updating imports, docs,
tests, and release notes together.

## Production Status

This repo is production-facing because it publishes the `charmos` package and
the public CLI. Preserve existing user-facing SDK, CLI, package, and
`charm.yaml` behavior unless the task explicitly changes it.

When changing public behavior:

- update docs,
- update package/release notes,
- add or update tests where practical,
- describe migration or compatibility impact in the PR.

## Release Hold

Do not publish from this repo unless the user explicitly requests a release.

- Do not create or push `v*` tags unless asked.
- Do not trigger production PyPI publishing unless asked.
- Do not treat configured Trusted Publishers or GitHub environments as release approval.
- Do not upload wheels or source distributions from a local machine for official releases.
- Do not introduce long-lived PyPI API tokens when Trusted Publishing is available.

Normal code pushes and TestPyPI dry runs are fine when requested.

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
docker build -f Dockerfile.standard -t charm-runner-standard:ci .
docker build -f Dockerfile.full -t charm-runner-full:ci .
```

## Docs Rules

- Keep `docs/docs.json` synchronized with actual `.mdx` files.
- OpenAPI groups in `docs/docs.json` validate the OpenAPI spec file, not generated operation pages.
- Avoid hidden TODO placeholders in public docs.
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

1. Is this a CLI command or local developer workflow? Put it in `src/charm/cli/`.
2. Is this part of `charm.yaml` or validation? Put it in `src/charm/contracts/`.
3. Is this framework-specific execution glue? Put it in `src/charm/adapters/`.
4. Is this runner orchestration, script generation, or protocol behavior? Put it in `src/charm/runner/`.
5. Is this backend-specific execution infrastructure? Put it in `src/charm/runner/backend/`.
6. Is this starter-agent content? Put it in `src/charm/templates/` and update docs.
7. Is this public usage guidance? Put it in `docs/`.

Key: a feature is not a CLI feature just because it can be triggered locally. If
it changes runtime execution, keep the source of truth in the runner or adapter
layer and let the CLI call into it.
