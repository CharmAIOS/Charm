# Contributing to Charm

Thanks for your interest in Charm!

Contributions are highly welcome. We’d love to gather any feedback you have on our feature modules, for example:

- Does the contract cover your agent’s configuration needs?
- Are there specific frameworks you’d like to see adapted next?

Let us know what you think.

If you’re interested in contributing to the core features and architecture of Charm, we’re actively looking for team members, feel free to [email us](mailto:uc@charmos.io) to chat.

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

2. Fork & Clone

```bash
git clone https://github.com/CharmAIOS/Charm.git
cd Charm
```

3. Create virtual environment

```bash
uv venv
source .venv/bin/activate
```

4. Install

```bash
uv pip install -e ".[runner,dev]"
```

5. Build Base Image (Required for Runner tests)

```bash
docker build -f Dockerfile.base -t charm-runner-base:latest .
```

6. Run Tests

```bash
pytest
```

## Issues, Bugs, and Feature Requests

1. Report bugs or suggest features under [Issues](https://github.com/CharmAIOS/Charm/issues/new/choose).
2. Before opening a new issue, please review the [existing issues](https://github.com/CharmAIOS/Charm/issues) first.
3. We kindly ask you to follow our issue templates.

## Community Guidelines

We follow the [contributing guidelines](https://docs.github.com/en/site-policy/github-terms/github-community-guidelines) to ensure respectful and collaborative contributions.
