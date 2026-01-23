# Charm Store: The App Store for AI Agents

Charm Store helps turn agent-based applications into real, commercial-ready products. Developers can ignore infrastructure and focus purely on agent logic. With standardized publishing, built-in application services and isolated runtimes, your code can become a complete product in minutes.

## Charm Store Compatibility & Constraints Guide (v1)

Please make sure to review our current technical specifications and limitations before publishing, to ensure your agent can run stably on the Charm Cloud Runner.

### Runtime & System Dependencies

#### Execution Environment

- Python Version: 3.12 (Fixed)
- Resources: 2 GB RAM, 1 vCPU, 600s Timeout
- Pre-installed Stack:
  - Data: pandas, numpy, scipy, requests, beautifulsoup4
  - Multimedia: ffmpeg, libgl1, opencv-python, pydub, moviepy.
  - For a complete list, verify our full [dockerfile.base](https://github.com/CharmAIOS/Charm/blob/main/Dockerfile.base)
- File System: Ephemeral (temporary). Artifacts generated during the run can be downloaded by the user.
- Internet Access: You can make API calls to external services (Outbound)

### Hard Limitations

- Frameworks: The SDK currently supports parsing and wrapping source agents built with **CrewAI, LangChain (Python), LangGraph, as well as custom Python agents**.
- Patterns: Charm support autonomous interaction patterns including single/multi-turn and reactive/proactive initiation, but currently does not support interrupted workflows (Human-in-the-Loop).
- System Installs: apt-get is disabled. System-level packages cannot be installed during execution (e.g., custom OCR drivers, Tesseract binaries, Chrome/Chromium).
- Local Environment / Private Venv: All Python packages must be declared in requirements.txt or pyproject.toml. If you modified a third-party library, vendor the modified source into your project (e.g., src/libs/) and import it from there.
- No Local Browsers: Selenium/Playwright setups requiring a local Chrome/Chromium will fail. Use API-based scraping (e.g., Tavily/Firecrawl) or requests + BeautifulSoup.
- No Heavy Local Models / GPU: Do not load local LLMs (e.g., Ollama) or large embedding models. No CUDA/GPU support (use cloud APIs instead).
- No Inbound Ports / Servers: Do not start servers that listen on inbound ports (e.g., Flask/FastAPI). The runner is not meant for hosting long-running web services.
- No Absolute Paths: The runner executes in a container, so your local filesystem paths won’t exist. Use relative paths inside the container (e.g., ./data/...) or construct paths from os.getcwd().

### Checklist

Before publishing, make sure:
- My agent is compatible with Python 3.12
- I am not using a local browser (Chrome / Selenium / Playwright)
- I am not loading local LLMs or large embedding models into memory
- All Python dependencies are listed in requirements.txt or pyproject.toml
- All file operations use relative paths
- All secrets are defined in charm.yaml, not in .env

> If you hit any issues, feel free to open an [issue](https://github.com/CharmAIOS/Charm/issues/new/choose) or ask in our [community](https://discord.gg/gdakynHUEb). It really helps us make the docs and product better.

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
