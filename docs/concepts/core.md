Charm is built upon four fundamental concepts that work together to transform isolated AI scripts into a governed, interoperable system.

>The current naming and descriptions are only temporary conceptual placeholders, intended to share our present design direction and solution approach with the community.
>
>We will continue to iterate and refine them based on implementation progress and feedback from participants. We warmly welcome you to join the discussion and help us improve and bring this to reality.

```mermaid
graph LR
    classDef dev fill:#fff3e0,stroke:#ff9800,stroke-width:2px;
    classDef store fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px,stroke-dasharray: 5 5;
    classDef runtime fill:#e1f5fe,stroke:#0277bd,stroke-width:2px;
    classDef object fill:#ffffff,stroke:#333;

    subgraph Developers [Developers / Ecosystem]
        direction TB
        Dev_A("Researcher Agent (CrewAI)")
        Dev_B("Google Search (LangChain Tool)")
        Dev_C("RAG Agent (LlamaIndex)")
    end

    subgraph Store [Charm Store & Registry]
        direction TB
        Catalog_Agent["Researcher Agent (CharmAgent)<br/>(Requires: GoogleSearch, RAG)"]
        Catalog_Tool["Google Search (CharmTool)"]
        Catalog_Sub["RAG Agent (Agent as a Tool)"]
    end

    subgraph User_Runtime [User Runtime / Sandbox]
        direction TB
        
        subgraph Running_Instance [Running Context]
            direction TB
            Agent_Instance("Researcher Agent<br/>(Running)")
            
            subgraph Injected_Capabilities [Injected Capabilities]
                Tool_Instance("GoogleSearch Tool")
                Sub_Instance("RAG Agent")
            end
        end
    end

    Dev_A -->|Publish UAC| Catalog_Agent
    Dev_B -->|Publish UTC| Catalog_Tool
    Dev_C -->|Publish UAC| Catalog_Sub

    Catalog_Agent ==>|User Installs| Agent_Instance
    
    Catalog_Agent -.->|declares dependency| Catalog_Tool
    Catalog_Agent -.->|declares dependency| Catalog_Sub
    
    Catalog_Tool -->|Auto-Download| Tool_Instance
    Catalog_Sub -->|Auto-Download| Sub_Instance

    Tool_Instance -->|Inject| Agent_Instance
    Sub_Instance -->|Inject| Agent_Instance

    class Dev_A,Dev_B,Dev_C dev;
    class Catalog_Agent,Catalog_Tool,Catalog_Sub store;
    class Agent_Instance,Tool_Instance,Sub_Instance object;
```

### CharmAgent
The CharmAgent serves as the standardized runtime executable within the ecosystem. It acts as a universal container that wraps agents built on any way, shielding the system from underlying implementation details. By enforcing the Unified Agent Contract (UAC), the CharmAgent normalizes inputs, outputs, and lifecycle behaviors, effectively transforming isolated, framework-specific logic into interoperable system components that can be managed, orchestrated, and injected with capabilities without requiring a code rewrite.
### CharmTool
CharmTool creates a neutral abstraction layer for external tools, services, and modules. It transforms them into standardized system capability modules that can be injected into CrewAI Agents, LangGraph workflows, or pure Python scripts, achieving a true decoupling of "capability" and "framework."
### Agent as a Tool
In Charm, a full-fledged intelligent agent can be wrapped and exposed as a simple CharmTool. This enables recursive composition, transforming agents from standalone entities into composable building blocks. Developers can use the exact same tool-use paradigm applied to CharmTools to construct complex, hierarchical multi-agent systems.
### Unified Runtime
The Unified Runtime serves as the "Operating System Kernel" for agentic applications. It is the execution environment responsible for reading the UAC, orchestrating the CharmAgent lifecycle, and performing Dependency Injection. The Runtime replaces the practice of hardcoding API keys and tools inside agents, instead dynamically provisioning resources, managing state persistence, and enforcing security policies at execution time. This ensures consistent agent behavior across local, cloud, or edge environments.
### Charm Store (Charm Agent Service)
The Charm Store serves as the application and service layer of the ecosystem. It includes a registry and a fully managed execution environment, providing unified authentication, secure payments, and credential-injection mechanisms.
By enforcing the Unified Agent Contract (UAC) within a governed sandbox, Charm ensures strict security, compliance, and operational integrity. It equips agents with critical system-level capabilities dynamically, transforming isolated agent scripts into trustworthy, commercially-grade, ready-to-use services.
