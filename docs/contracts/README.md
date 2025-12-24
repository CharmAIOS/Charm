## Charm Unified Contracts

Charm adopts a **Contract-First Architecture**, meaning the system is structured around a set of stable, versioned, and framework-agnostic contracts.

A contract in Charm is not a data model or internal struct. It is a formal interoperability specification that defines interface protocols, dependency requirements, and runtime behaviors.

Charm Contracts define neutral agent representations, execution envelopes, adapter configurations, and error semantics, ensuring that Charm can govern and orchestrate heterogeneous ecosystems.

### Contract Suite Roadmap
Charm defines four key contracts:

1.  **Unified Agent Contract (UAC)** `[Active v0.4.0]`
    * **Purpose:** Defines the agent's identity, interface protocol, and runtime adapter configuration.
    * **Role:** The **Driver Descriptor** that allows Charm to load and wrap any agent.

2.  **Unified Tool Contract (UTC)** `[Planned]`
    * **Purpose:** Standardizes the definition of external tools (APIs, databases) and their authentication requirements.
    * **Role:** Enables the runtime to perform **Dependency Injection**, dynamically providing capabilities to agents without hardcoded logic.

3.  **Interaction & Error Contract (IEC)** `[Planned]`
    * **Purpose:** Standardizes error codes, interrupt signals, and state handoff protocols.
    * **Role:** Ensures the runtime can handle failures gracefully and manage HITL interactions across different frameworks.

4.  **Workflow Composition Contract (WCC)** `[Planned]`
    * **Purpose:** Defines how multiple agents are chained or orchestrated into a larger system.
    * **Role:** The blueprint for multi-agent collaboration in the future Execution Layer.

---

> **Status Note:**
> In the current **v0.4.10 Developer Preview**, only the **UAC** is active and enforced.
>
> **Note on Stability:** The **UTC, IEC, and WCC** are **provisional specifications** and are subject to change based on community feedback. We welcome everyone to help shape these standards.









