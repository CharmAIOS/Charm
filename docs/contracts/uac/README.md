## Charm Unified Agent Contract (UAC) Specification v0.2.0

The Unified Agent Contract (UAC) is Charm’s cross-framework semantic standard. It defines a neutral, portable, and framework-agnostic representation of an agent.

The UAC serves as the central contract that allows Charm to:
- Standardize: Define an agent's interface, state schema, and dependencies in a unified semantic format.
- Bridge: Provide the necessary metadata for Charm Adapters to wrap and execute agents from heterogeneous frameworks.
- Distribute: Serve as the canonical manifest for the Charm Registry, enabling agents to be versioned, discovered, and governed.
### Objectives

- Semantic Neutrality: To provide a universal definition layer independent of any specific underlying framework or runtime implementation.
- Interoperability Base: To serve as the source of truth for the Charm Runtime, guiding how adapters should load agents and inject dependencies.
- Registry & Governance: To allow agents to be packaged, synchronized, and redistributed across ecosystems with clear permission boundaries.

### Contract Scope

Charm treats the UAC as a **declarative description** of the agent.
#### Included in the Contract (Portable)
* Identity (`persona`): Agent name, description, authors, license, and metadata.
* Interface Protocol (`interface`):
    * I/O definitions (Input/Output JSON Schemas).
    * Persistent State structure (for snapshotting and restoration).
* Runtime Configuration (`runtime`):
    * Adapter Selection: Specifies which SDK adapter to use (e.g., `charm.adapters.crewai`).
    * Dependency Injection: Explicitly declares required resources (e.g., `tools`, `llm_client`) to be injected by the runtime.
* Governance (`policies`): Permission scopes, human-in-the-loop triggers, and resource limits.
* Observability (`workflow`): Descriptive graphs (nodes + edges) for visualization and documentation.

#### Excluded from the Contract (Runtime Bound)
* Execution Environment: API keys, secrets, specific endpoint URLs, and infrastructure-level settings are **NOT** part of the UAC. These are bound dynamically at runtime via the Charm Bridge / Environment Variables.

### Design Principles

1.  Core Descriptive Set: Defines the fundamental semantic structure shared by all agents (Identity, Interface, Adapter).
2.  Dependency Injection First: The contract explicitly declares *what* the agent needs (e.g., "Google Search Tool"), leaving the *how* (actual API client instantiation) to the Charm Runtime.
3.  Extensible Namespace: Any field can be extended via `x-namespace` properties to support framework-specific metadata without breaking the standard.
4.  Descriptive Observability: For black-box agents (e.g., compiled binaries or complex code), the internal workflow graph serves as a documentation layer for observability, rather than an execution instruction.

### Versioning & Compatibility Policy

* Semantic Versioning: Every UAC file must include a `version` field.
* Backward Compatibility: New fields are optional by default.
* Breaking Changes: Major version bumps require an upgrader script or migration guide for older contracts.

### Important Clarification

> The UAC is a semantic contract, not executable code.

* It does not contain the agent's logic.
* It is not a packaging system.
* It **mirrors and describes** the structure of the source agent, telling the Charm Runtime how to interact with it.

#### Structure Mapping Examples

| Source Framework | UAC Runtime Configuration |
| :--- | :--- |
| **CrewAI** | Specifies `adapter.type = "crewai"`. Runtime loads the Crew structure and injects tools via the adapter. |
| **LangChain** | Specifies `adapter.type = "langchain"`. Runtime wraps the Chain/Graph and maps the state schema. |
| **Custom Code** | Specifies `adapter.type = "custom"`. Runtime loads the specified python class entry point. |

### Details
Unified Agent Contract (v0.2.0)
