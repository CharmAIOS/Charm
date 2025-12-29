# Charm Store: The App Store for AI Agents

Charm Store helps turn agent-based applications into real, commercial-ready products. Developers can ignore infrastructure and focus purely on agent logic. With standardized publishing, built-in application services and isolated runtimes, your code can become a complete product in minutes.

## Zero-Ops Publishing

Register your agent on the Charm Store.

> If you’re using uv, please prefix all commands with uv run.

1. Authentication
Sign in to the Charm platform and link your account.

```bash
charm auth login
```

2. Preparing your UAC manifest

Refer to [this document](https://github.com/CharmAIOS/Charm/blob/main/docs/contracts/uac/configuration.md) for guidance on how to author a charm.yaml.

3. Local Validation & Development

Step A: Static Analysis

Use Pydantic to validate that the YAML fields conform to the UAC schema.

```bash
charm validate .
```

Step B: Local Execution

Run your agent using your local Python environment. This is best for rapid logic iteration and debugging.

**Option 1**: Simple Text Input

Use this if your agent accepts a single string (e.g., a prompt or a topic).

```bash
charm run . --input "YOUR_INPUT_TEXT"
```

**Option 2**: JSON Payload

Use this if your agent requires multiple parameters (as defined in interface.input).

```bash
charm run . --json '{"field_name": "value", "option_key": 123}'
```

> field_name: Must match the property names defined in your charm.yaml.
> 
> value: The actual data you want to pass to the agent.

Step C: Sandbox Simulation (Best to have)

Run your agent inside the Charm Docker Sandbox. This guarantees compatibility with the cloud runtime.

```bash
charm run . --input "YOUR_INPUT_TEXT" --docker
```

> Prerequisite: Ensure you have installed the runner extras (pip install "charmos[runner]") and Docker is running.

4. Publishing

```bash
charm push
```

## What does Charm do?

### Agent Encapsulation

The Charm SDK transforms your agent into a unified capability component, allowing it to be consistently described, executed, and invoked.

### Secure Sandbox & Runtime Governance

Charm provides agents with an out-of-the-box Secure Runtime.
It uses isolated sandbox execution to dynamically injects state, memory, and execution dependencies at runtime. Each agent runs in a dedicated, controlled environment with support for pausing and resuming long-running tasks, effectively preventing malicious behavior and resource contention.

All API keys are injected only at execution time and exist solely in memory. Using an ephemeral, use-once model, sensitive credentials are never written to disk or persisted, ensuring security guarantees by default.

### The Storefront

Generates a contract-driven UI from the manifest, instantly creating a web chat interface and securely handling user keys through encryption.
