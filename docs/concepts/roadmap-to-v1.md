## Charm v1.0 Overview: The Road to the AI App Store

Charm v1.0 will focus on establishing the application layer and the Charm Store, enabling agent-based applications to evolve from code prototypes into fully commercializable products, and finally bringing real AI value into the world.

In v1.0, users will be able to:

- Publish an agent directly from their terminal using `charm push`.
- Discover a wide variety of agents on the Charm Store.
- Run agents instantly in the cloud without setting up any environment.
- Interact with all agents through a unified frontend interface.

### Where We Are (v0.2.0)
Current Status: Building the **Universal Interface**

We introduce a standard packaging format that defines how agents are wrapped and executed on Charm (much like the `.ipa` and `.apk`)

Current Deliverables:

Unified Agent Contract (UAC): The manifest that describes an agent.

Charm SDK: The wrapper that lets agents run via a standard interface.

### The Path to v1.0
To reach the v1.0 launch, we have broken down our roadmap into four distinct stages:

#### Phase 1: The Foundation (Current Focus)
See [here](https://github.com/CharmAIOS/Charm/blob/main/docs/concepts/v0.2.0.md) for details.
#### Phase 2: The Distribution Layer
building the Registry—the index of the Charm ecosystem.

Key Modules:

Charm CLI: A command-line tool to verify and push agents (`charm auth`, `charm push`).

Registry Backend: A database storing agent metadata, UAC configs, and pointers to source code.

#### Phase 3: The Unified Runtime

Building a secure, serverless environment that can pull an agent from the Registry and execute it.

Key Modules:

Serverless Runner: A containerized environment that auto-builds based on the UAC Adapter type.

Secret Injection System: Securely injecting API keys at runtime.

Standard Output Stream: Converting agent thoughts/responses into a real-time web stream (SSE).

Success Metric: Sending a curl request to the Runtime API successfully executes a hosted agent.

#### Phase 4: The Storefront

Build a user-facing platform where non-technical users can interact with agents seamlessly.

Key Modules:

Web Store UI: Browse, search, and view agent details (Icon, Pricing, Description).

Universal Chat Interface: A chat UI that dynamically renders inputs based on the UAC definition.

## Beyond v1.0: Unlocking System-Level Composability

Our v1 release prioritizes the **Distribution**, delivering the first end-to-end **Agent Store** experience to help agents achieve immediate value realization and market reach. 

Looking beyond v1, we plan to expand into **Ecosystem Aggregation**, introducing features like **CharmTools** and **Agent-as-a-Tool**, allowing any agent to seamlessly utilize external capabilities and other agents from the ecosystem as modular building blocks.
