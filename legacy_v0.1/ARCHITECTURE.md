## Charm Middleware Architecture

### Flow Visualization
```mermaid
flowchart LR
    subgraph FrameworkA["Source Framework"]
        A1[Role Card / Graph / Profile]
    end

    subgraph Charm["Charm Middleware"]
        C1[Adapter]
        C2[Event Bridge]
        C4[Transport]
        C5[Edge Hook]
    end

    subgraph FrameworkB["Target Framework"]
        B1[Agent Execution]
    end

    %% Flow
    A1 --> C1
    C1 --> C2
    C2 --> C4
    C4 --> C5
    C5 --> B1
    B1 --> C5 --> C4 --> A1
```
### Core Modules
#### Agent Adapter
The Agent Adapter handles the entire portability pipeline: it parses source-framework agent definitions, normalizes them into a Unified Agent Contract (uac), resolves all semantic fields (role, capabilities, workflow), and compiles the result into a runnable profile for the target framework. It ensures that one agent definition can be executed across different ecosystems without rewriting logic.

#### Stateful Bridge
The Stateful Bridge connects execution between frameworks. It converts runtime steps into event streams, sends them to the target framework, and reattaches incoming results to the correct task or node. Allowing a single agent flow to span multiple frameworks while remaining logically continuous.

#### Transport 
Transport provides the bidirectional communication channel. It delivers events between Charm and external frameworks with low latency, handles encoding, routing, ordering, and correlation IDs, and ensures every message reaches the correct session, task, or node.

#### Edge Governance
Edge Governance enforces resource and execution policies at the system boundary. It applies rate limits, quotas, concurrency rules, and retry/backoff strategies to all cross-framework events, ensuring stable execution and safe fallback behavior during portability or bridge operations.
