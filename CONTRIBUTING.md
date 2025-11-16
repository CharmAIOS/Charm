## Contributing to Charm

Thanks for your interest in Charm.

We’re currently building our v1 release, featuring a federated runtime and middleware layer.

See the [docs](https://github.com/CharmAIOS/Charm/tree/main/docs) to learn more about Charm.


## Getting Started
See [this](https://github.com/CharmAIOS/Charm/blob/main/docs/dev_setup.md) for detailed setup instructions.

## How to Contribute
1.	Create a new branch from main
    ```bash
    git checkout -b feat/<your-feature-name>

2.	Make your changes and commit
    ```bash
    git commit -m "feat: describe your change here"

3.	Push your branch and open a Pull Request
    ```bash
    git push origin feat/<your-feature-name>
4.	Describe:
- What you changed
- Why it’s needed
- How reviewers can validate the update

### Development Workflow

1.	Check [contracts](https://github.com/CharmAIOS/Charm/tree/main/docs/contracts/uac) to confirm the current frozen schemas.
2.	Choose a [route](https://github.com/CharmAIOS/Charm/blob/main/docs/pipeline.md) and open an Issue using the corresponding template (For now, Charm focuses on a single reference route:
**CrewAI → LangGraph**).
3.	Use the provided [fixtures](https://github.com/CharmAIOS/Charm/tree/main/fixtures/crewai-research-agent)
   as the “golden sample.”
4.	Submit a PR.
5.	Run the route test:
    ```bash
    python tests/fixtures/test_fixture_smoke.py
## Issues, Bugs, and Feature Requests
1. Report bugs or suggest features under Issues
2. Check existing issues
3. Follow the issue templates

You can read the [contributing guidelines](https://opensource.guide/) before you begin

## Current Development Focus
We’re currently prioritizing **Agent Portability** — building the core pipeline that makes agents portable across frameworks.

Please familiarize yourself with:
- [**Pipeline Overview**](https://github.com/CharmAIOS/Charm/blob/main/docs/pipeline.md)
- [**Contracts**](https://github.com/CharmAIOS/Charm/blob/main/docs/contracts/uac/README.md)
- [**Fixtures**](https://github.com/CharmAIOS/Charm/tree/main/docs/fixtures)

Contributions related to this are highly welcome. If you want to help in one of these areas, comment under the relevant GitHub Issue or @ucmind in Discussions.

## Community Guidelines
We follow the [contributing guidelines](https://docs.github.com/en/site-policy/github-terms/github-community-guidelines) to ensure respectful and collaborative contributions.

