## Charm Store: The App Store for AI Agents

Charm Store helps turn agent-based applications into real, commercial-ready products. Developers can ignore infrastructure and focus purely on agent logic. With standardized publishing, built-in application services and isolated runtimes, your code can become a complete product in minutes.

### Zero-Ops Publishing
> If you’re using uv, please prefix all commands with uv run.
1. Authentication
Sign in to the Charm platform and link your account.
```bash
charm auth login
```
2. Preparing your UAC manifest

Refer to [this document](https://github.com/CharmAIOS/Charm/blob/main/docs/contracts/uac/configuration.md) for guidance on how to author a charm.yaml.

3. Local Validation

- Static Analysis

Use Pydantic to validate that the YAML fields conform to the UAC schema.
```bash
charm validate .
```
- Local Execution

Simulate the Cloud Runner locally to ensure your agent accepts inputs correctly.

**Option 1: Simple Text Input**

Use this if your agent accepts a single string (e.g., a prompt or a topic).
```bash
charm run . --input "YOUR_INPUT_TEXT"
```
**Option 2: JSON Payload**

Use this if your agent requires multiple parameters (as defined in interface.input).
```bash
charm run . --json '{"field_name": "value", "option_key": 123}'
```
> field_name: Must match the property names defined in your charm.yaml.
> value: The actual data you want to pass to the agent.

4. Publishing
```bash
charm push
```
### Secure Sandbox & Runtime Governance
Automatically provides an enterprise-grade execution environment for every agent execution.

Ephemeral Isolation: Each task runs inside an isolated, stateless Micro-VM.
The execution environment is destroyed immediately after the task completes, ensuring absolute runtime privacy and isolation.

Secure Secret Injection: Supports BYOK via encrypted channels. Your code only reads environment variables, while Charm securely manages and injects sensitive credentials at runtime.
Secrets are never written to disk.

Dynamic Environment Management: Automatically builds and locks the dependency graph based on the UAC manifest. This eliminates environment inconsistencies and enables true “write once, run anywhere.”

Guardrails & Oversight: Built-in enforcement of resource quotas and execution timeouts. Ensures production-grade stability and reliability for agent-based services.

#### The Storefront 
Charm generates a contract-driven UI from the manifest and instantly produces a web chat interface without requiring any frontend code, making it accessible to non-technical users.

## Agent as a tool
TBD


