# CLAUDE.md

This file provides specialized guidance for Claude Code when working in the Charm SDK repository.

> **CRITICAL: Read [AGENTS.md](AGENTS.md) first.**  
> `AGENTS.md` is the absolute source of truth for repository boundaries, development commands, release rules, and placement decisions. You must adhere to the rules in `AGENTS.md` above all else.

## Start Here

Before modifying specific areas of the repository, review these key files:

- Read `pyproject.toml` before changing package metadata, dependencies, entry points, or release behavior.
- Read `.github/workflows/ci.yml` before changing CI checks.
- Read `.github/workflows/publish-testpypi.yml` and `.github/workflows/publish-pypi.yml` before changing package publishing.
- Read `docs/oss/release-process.mdx` before changing release process docs.
- Read `docs/docs.json` before changing docs navigation.

## Claude-Specific Review Priorities

- **Maintain Stability:** Keep SDK, CLI, `charm.yaml`, and package behavior stable for existing users.
- **Treat Configs as Code:** Treat docs, package metadata, runtime images, and release workflows as public surfaces.
- **Accuracy Over Speed:** Keep changelog labels and PR release notes precise and accurate.
- **Rigorous Validation:** Validate OpenAPI docs navigation through the referenced spec file.
- **Never Relax CI:** Never relax checks just to make CI green. Fix the underlying issue or document a narrow, justified exception.

## Don't

- Do not commit secrets, tokens, `.env` files, or service account keys.
- Do not add duplicate helpers with overlapping ownership.
- Do not hide third-party integration failures behind broad fallbacks.
- Do not create compatibility shims for unshipped branch-only behavior unless requested.
- Do not make package publishing depend on a maintainer's local machine.
