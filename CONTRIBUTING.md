# Contributing to Charm

Thanks for your interest in Charm!

Contributions are always welcome. We’d love to build the future with you, whether through new features, improved infrastructure, better documentation, or bug fixes.

## Join the Conversation

We’re active on [Discord](https://discord.gg/gdakynHUEb). Jump in to share ideas, ask questions, and connect with others.

## How to Contribute

1. Fork the repository.
2. Create a new branch for your feature or fix.
3. Commit your changes.
4. Submit a Pull Request
5. Describe:

- What you changed
- Why it’s needed
- How reviewers can validate the update

## Dev Setup

1. Prerequisites

- Python **3.10+**
- `git`
- [uv](https://github.com/astral-sh/uv)

1. Fork & Clone

```bash
git clone https://github.com/CharmAIOS/Charm.git
cd Charm
```

1. Create virtual environment

```bash
uv venv
source .venv/bin/activate
```

1. Install

```bash
uv pip install -e ".[runner,dev]"
```

1. Build Base Image (Required for Runner tests)

```bash
docker build -f Dockerfile.base -t charm-runner-base:latest .
```

1. Run Tests

```bash
pytest
```

## Issues, Bugs, and Feature Requests

1. Report bugs or suggest features under [Issues](https://github.com/CharmAIOS/Charm/issues/new/choose).
2. Before opening a new issue, please review the [existing issues](https://github.com/CharmAIOS/Charm/issues) first.
3. We kindly ask you to follow our issue templates.

## Community Guidelines

We follow the [contributing guidelines](https://docs.github.com/en/site-policy/github-terms/github-community-guidelines) to ensure respectful and collaborative contributions.
