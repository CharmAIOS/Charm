## Charm Unified Agent Contract Specification

### Objectives

- Semantic Neutral Layer: Describe an agent in a framework-agnostic manner
- Portability and Mapping: Enable any source definition to be converted into a Unified Agent Contract (UAC), which can then be rendered into any target framework
- Minimal Sufficient Set: Provide a minimal yet complete set of fields covering persona, goals, capabilities, constraints, tools, workflow (nodes/edges), policies, etc.

Charm treats the following as part of an agent’s portable contract:
- Definition: persona, goals, capabilities, workflow, policies
- Portable configuration: model preferences, interaction style, tools, and mapping hints

Execution environment details (credentials, endpoints, infra-level settings) are **not** part of the UAC and are bound at runtime via Charm’s bridge and target loaders.

### Design Principles

1. Core Descriptive Set: Defines the core semantic structure shared by all agents
2. Optional Submodules: Additional layers designed for agents with different input types (prompt-based or graph-based)
3. Extensible Namespace: Allow objects at any level to be extended via prefixed fields
4. Unknown Node Handling: When the source framework contains nodes that are currently unsupported or cannot be equivalently converted, mark them and use x-original to preserve the complete original definition segment for future processing
5. Equivalence and degradation annotations: The conversion process should indicate support levels such as fully equivalent, unsupported, etc.

### Versioning & Compatibility Policy

- Every UAC must include a version field
- New fields should be optional by default to maintain backward compatibility
- For breaking changes:
    - Bump the major version
    - Provide an upgrader script to migrate older contracts

### Details
[Unified Agent Contract](https://github.com/CharmAIOS/Charm/blob/main/docs/contract/uac.schema.json) (v0.1.0)

[Minimal Valid UAC Object Example](https://github.com/CharmAIOS/Charm/blob/main/docs/fixtures/crewai-research-agent/uac.sample.json) (CrewAI)
