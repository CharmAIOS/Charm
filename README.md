<p align="center">
  <img src="assets/charm-banner.png" alt="Charm Banner" width="60%" />
</p>

<p align="center">
  <a href="https://github.com/CharmAIOS/Charm/actions"><img src="https://img.shields.io/github/actions/workflow/status/CharmAIOS/Charm/deploy-staging.yml?label=BUILD&style=flat-square&color=E8A694" alt="Build" /></a>
  <a href="https://pypi.org/project/charmos/"><img src="https://img.shields.io/pypi/v/charmos?label=RELEASE&style=flat-square&color=007ec6" alt="PyPI" /></a>
  <a href="https://discord.gg/gdakynHUEb"><img src="https://img.shields.io/badge/DISCORD-JOIN%20US-5865f2?style=flat-square&logo=discord&logoColor=white" alt="Discord" /></a>
  <a href="https://github.com/CharmAIOS/Charm/blob/main/LICENSE"><img src="https://img.shields.io/github/license/CharmAIOS/Charm?label=LICENSE&style=flat-square&color=007ec6" alt="License" /></a>
  <a href="https://x.com/charm_labs"><img src="https://img.shields.io/twitter/follow/charm_labs?label=FOLLOW%20@CHARM_LABS&style=flat-square&color=000000&logo=x&logoColor=white" alt="X" /></a>
</p>


# Charm: The Unified Platform for Agentic Intelligence

**Charm** is a **Unified Application Layer** that enables agents to distribute, run, and scale across heterogeneous ecosystems, turning them into real, commercial-ready applications.

## Getting Started

For a step-by-step walk through of Charm concepts and code, check out [overview](https://docs.charmos.io) in our documentation.

### Installation

Charm is available on PyPI. We recommend using [uv](https://github.com/astral-sh/uv) for the best experience.

#### Standard Setup (For Agent Development)

If you only want to build and define agents

```bash
uv add charmos
# or
pip install charmos
```

#### Advanced Setup (For Local Cloud Runner)

If you want to simulate the isolated cloud environment locally

```bash
uv add charmos[runner]
# or
pip install charmos[runner]
```

> **Note:** To use the docker simulation mode, you must have Docker Desktop or Docker Engine running on your machine.
>
### Build and publish your first agent

Use the quickstart docs to install the CLI, build a starter agent, validate `charm.yaml`, and publish to Charm Store:

- [Installation](https://docs.charmos.io/quickstart/install)
- [Build Your First Agent](https://docs.charmos.io/quickstart/first-app)
- [Publish](https://docs.charmos.io/quickstart/publish)

## Documentation

- [Templates](https://docs.charmos.io/templates/overview)
- [Platform Features](https://docs.charmos.io/platform/features)
- [CLI Reference](https://docs.charmos.io/cli/init)
- [SDK Reference](https://docs.charmos.io/references/sdk)
- [Open Source](https://docs.charmos.io/oss/overview)

## Contributing

To know how to contribute to Charm, please read our [contribution guide](https://github.com/CharmAIOS/Charm/blob/main/CONTRIBUTING.md).

## Security

Please report vulnerabilities privately using the process in [SECURITY.md](./SECURITY.md).

## Contact

- Support and Questions: [Community](https://discord.gg/gdakynHUEb) / [Email](mailto:team@charmos.io)
- Join us: [Chat with the team](mailto:team@charmos.io)

## Changelog

Check our [updates](https://charmos.io/changelog)

## License

Charm is licensed under the [GNU Affero General Public License v3.0](https://github.com/CharmAIOS/CharmOS/blob/main/LICENSE)
