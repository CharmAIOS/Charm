## Charm Unified Agent Contract Specification

The Unified Agent Contract (UAC) is Charm’s cross-framework semantic contract that defines a neutral, portable, framework-agnostic representation of an agent.

It serves as the central contract that Charm uses to:
- Serialize an agent into a standardized semantic format
- Preserve all information needed for portability across frameworks
- Enable deterministic rendering into multiple target runtimes
- Maintain cross-framework consistency for workflow structure, capabilities, and execution semantics

### Objectives

- Semantic Neutral Layer: Provide a neutral agent definition independent of any framework or runtime.
- Portability and Mapping:  Serves as the basis for transformations performed by the agent parser and renderer.
- Registry: UAC also serves as the canonical definition stored in Charm’s Registry, allowing agents to be versioned, synchronized, and redistributed across ecosystems

Charm treats the following as part of an agent’s portable contract:
- Definition: persona, goals, capabilities, workflow (nodes + edges), policies
- Portable configuration: model preferences, interaction style, tools, and mapping hints

Execution environment details (credentials, endpoints, infra-level settings) are **not** part of the UAC and are bound at runtime via Charm’s bridge and target loaders.

### Design Principles

1. Core Descriptive Set: Defines the core semantic structure shared by all agents.
2. Optional Submodules: Additional layers designed for agents with different input types (e.g., prompt-based agents or graph-based multi-agent systems).
3. Extensible Namespace: Any field can be extended via x-namespace.
4. Unknown Node Handling: When the source framework contains nodes that are currently unsupported or cannot be equivalently converted, mark them and use x-original to preserve the complete original definition segment for future processing.
5. Equivalence and degradation annotations: The conversion process should indicate support levels such as fully equivalent, unsupported, etc.

### Versioning & Compatibility Policy

- Every UAC must include a version field
- New fields should be optional by default to maintain backward compatibility
- For breaking changes:
    - Bump the major version
    - Provide an upgrader script to migrate older contracts

### Important Clarification

The UAC is not a runtime object and does not contain executable code. It is a cross-framework semantic contract.

A UAC may contain:
- One agent (most cases)
- Multiple agents (when the source framework defines a multi-agent system)

But UAC is not a packaging or bundling system.

It simply mirrors the source framework’s structure.

Examples:
|Source Framework|UAC Structure|
|--------|-------------------------------------------------------------------------------------------------------|
| CrewAI   | UAC.agents = list of agents   |
| LangChain      |  UAC.agents = 1 |
| Single-file custom agent     | UAC.agents = 1 |

### Details
[Unified Agent Contract](https://github.com/CharmAIOS/Charm/blob/main/docs/contract/uac.schema.json) (v0.1.0)

[Minimal Valid UAC Object Example](https://github.com/CharmAIOS/Charm/blob/main/docs/fixtures/crewai-research-agent/uac.sample.json) (CrewAI)
