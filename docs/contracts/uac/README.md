# Charm Unified Agent Contract (UAC) Specification

The Unified Agent Contract (UAC) is Charm’s cross-framework semantic standard. It defines a neutral, portable, and framework-agnostic representation of an agent.

The UAC serves as the central contract that allows Charm to:

- Standardize: Define an agent's interface, state schema, and dependencies in a unified semantic format.
- Bridge: Provide the necessary metadata for Charm Adapters to wrap and execute agents from heterogeneous frameworks.
- Distribute: Serve as the canonical manifest for the Charm Store, enabling agents to be versioned, discovered, and governed.

## Objectives

- Semantic Neutrality: To provide a universal definition layer independent of any specific underlying framework or runtime implementation.
- Interoperability Base: To serve as the source of truth for the Charm Runtime, guiding how adapters should load agents and inject dependencies.
- Registry, Commerce & Governance: To allow agents to be packaged with commercial metadata and security policies for trusted distribution in a marketplace.

## Contract Scope

Charm treats the UAC as a **declarative description** of the agent:

### Presentation & Commerce (Store Layer)

- Identity (`persona`):
  - Basic Info: Name, short tagline, authors, and license.
  - Storefront Content: `full_description` for the rich detail page.
  - Visual Assets (`assets`): Icons, banners, and screenshots for store display.

- Business Model (`pricing`): Defines whether the agent is free, paid (usage-based/one-time), or subscription-based.
- Discovery (`goals`): Semantic tags used by the Store's search engine to index the agent's capabilities and intent.

### Execution & Protocol (Runtime Layer)

- Interface Protocol (`interface`):
  - I/O Definitions:*JSON Schemas defining inputs and outputs.
  - UI Hints: Supports `x-ui-widget` annotations to enable **Instant UI Generation** (e.g., auto-generating forms, text areas, or file uploads).
  - State Schema: Structure of the persistent state for snapshotting and restoration.

- Runtime Configuration (`runtime`):
  - Adapter Selection: Specifies which SDK adapter to use (e.g., `adapter.type = "crewai"`) and the code entry point.
  - Dependency Injection: Explicitly declares required resources (e.g., `tools`, `llm_client`) to be injected dynamically by the runtime.

### Safety & Control (Governance Layer)

- Governance (`policies`):
  - Permission Scopes: `allow_internet_access`, `allow_file_write`.
  - Human Oversight: `human_in_the_loop` triggers for sensitive actions or keywords.
  - Resource Limits: Budget caps and max execution steps.

### Excluded from the Contract (Runtime Bound)

- Execution Environment: API keys, secrets, specific endpoint URLs, and infrastructure-level settings are **NOT** part of the UAC. These are bound dynamically at runtime via the Charm Bridge.

### Design Principles

1. Core Descriptive Set: Defines the fundamental semantic structure shared by all agents (Identity, Interface, Adapter).
2. Dependency Injection First: The contract explicitly declares what the agent needs (e.g., "Google Search Tool"), leaving the how (actual API client instantiation) to the Charm Runtime.
3. Descriptive Observability: For black-box agents, the internal workflow graph serves as a documentation layer for observability, rather than an execution instruction.

### Versioning & Compatibility Policy

- Semantic Versioning: Every UAC file must include a `version` field.
- Backward Compatibility: New fields are optional by default.
- Breaking Changes: Major version bumps require an upgrader script or migration guide for older contracts.

### Important Clarification

> The UAC is a semantic contract, not executable code.

- It does not contain the agent's logic.
- It is not a packaging system.
- It **mirrors and describes** the structure of the source agent, telling the Charm Runtime how to interact with it.

## Structure Mapping Examples

| Source Framework | UAC Runtime Configuration |
| :--- | :--- |
| **CrewAI** | Specifies `adapter.type = "crewai"`. Runtime loads the Crew structure and injects tools via the adapter. |
| **LangChain** | Specifies `adapter.type = "langchain"`. Runtime wraps the Chain/Graph and maps the state schema. |
| **Custom Code** | Specifies `adapter.type = "custom"`. Runtime loads the specified python class entry point. |

- [Unified Agent Contract (v0.4.1)](https://github.com/CharmAIOS/Charm/blob/main/src/charm/contracts/uac.v0.4.1.schema.json)
