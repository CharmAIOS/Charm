# Configuration Guide: The UAC Manifest

## Getting Started

Depending on your project status, choose the path that fits you best.

Path A: Start a new project

```bash
charm init my-agent # --template skill (for OpenClaw Agent)
cd my-agent
```

Path B: Create the file manually

1. Create a file named charm.yaml in your project root

> The charm.yaml file must always be at the root level of your project

```plaintext

my-agent/             <-- Project Root
├── charm.yaml        <-- The Manifest
├── pyproject.toml / requirements.txt / package.json   <-- Dependencies
└── src/
    └── main.py       <-- Your Agent Logic
```

1. Copy the Annotated Reference below for use in your configuration

2. Update the field with your existing agent project

### IDE Setup

By configuring your editor, you get auto-completion and error checking. This is crucial for avoiding typos.

1. Create .vscode/settings.json in your project root.

```JSON
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/CharmAIOS/Charm/main/src/charm/contracts/uac.v0.4.1.schema.json": "charm.yaml"
  }
}
```

### Annotated Reference

This is a fully annotated example to understand specific capabilities or customization options.

```YAML

# ==================================================================
# Charm Agent Manifest (Annotated Reference)
# ==================================================================

version: "0.4.1"  # [System] The UAC Spec version (Do not change manually).

# ------------------------------------------------------------------
# 1. Identity & Store Metadata
# ------------------------------------------------------------------
persona:
  name: "My Charm Agent" # Display Project Name (Max 50 chars)
  version: "0.1.0" # [Agent] Your Agent's Semantic Version. Update this when publishing updates.
  description: "A short description of this agent." # Tagline (Card view, Max 100 chars)
  
  # Full description supports Markdown. Used for the Info Page.
  full_description: |
    # My Charm Agent
    ...
  # Describe usage, available capabilities, and expected deliverables.
    
  authors: ["Brand, Company, or Individual Name"]
  tags: ["research", "productivity"] # We use tags to categorize agents for users, so please make sure your first tag is one of Productivity, Developer, Creative, Learning, Lifestyle, Search & News, or Others.
  license: "MIT"
  
  # Assets for the Storefront
  assets:
    icon: "https://your-site.com/assets/icon.png" # 512x512 Square
    banner: "https://your-site.com/assets/banner.png"  # 1200x600 Wide

pricing:
  type: "free"  # Options: free, usage_based, one_time, subscription. At this stage, please fill in free.

# ------------------------------------------------------------------
# 2. UI Generation
# ------------------------------------------------------------------
# Defines the input form shown to users.
# It uses standard JSON Schema.
interface:
  input:
    type: "object"
    required: ["topic"] # Mandatory fields
    properties:
      # Example 1: Simple Text Input
      topic:
        type: "string"
        title: "Research Topic"
        default: "AI Agents"
      
      # Example 2: Large Text Area
      details:
        type: "string"
        title: "Extra Details"
        description: "Paste any background info here."
        x-ui-widget: "textarea" 
      
      # Example 3: File Upload
      # The Runner will download the file and inject the filename into this variable.
      document:
        type: "string"
        title: "Upload Document"
        x-ui-widget: "file" 

      # Example 4: Number Input
      depth:
        type: "integer"
        title: "Search Depth"
        default: 3
        minimum: 1
        maximum: 5

  output:
    type: "object"
    description: "The structure of the final result."

# ------------------------------------------------------------------
# 3. Runtime Configuration
# ------------------------------------------------------------------
runtime:
  adapter:
    # - crewai / langchain / langgraph : Standard Python Frameworks
    # - openclaw : Configuration-driven Agent
    # - node : For JavaScript/TypeScript Agents
    # - custom : Pure Python functions
    type: "crewai"
    
    # --------------------------------------------------------------
    # ENTRY POINT: Where is your agent object?
    # Format: <python_module_path>:<variable_or_function_name>
    #         OR <shell_command> (for Node.js)
    # --------------------------------------------------------------
    # [Case A] For Frameworks (CrewAI, LangChain): Point to the agent instance.
    entry_point: "src.main:my_crew"
    
    # [Case B] For Custom (Pure Python): Point to a function or class instance.
    entry_point: "src.my_script:run_pipeline"

    # [Case C] For Node.js (Remotion, Puppeteer, etc.): Provide the shell command.
    entry_point: "npm start"

    # [Case D] For OpenClaw: Optional (uses default host if empty)
    entry_point: ""
    
    # --------------------------------------------------------------
    # SECURE ENV VARS: List keys your agent needs.
    # DO NOT put values here. The Runner injects them securely.
    # --------------------------------------------------------------
    environment_variables:
      - "OPENAI_API_KEY"
      - "SERPER_API_KEY"

  # --------------------------------------------------------------
  # SKILLS & MCP TOOLS
  # --------------------------------------------------------------
  skills:
    
    # [Source: Git] 
    - name: "research-flow"
      source: "git:https://github.com/openclaw/skill-researcher"
      version: "main" # Or Commit Hash / Tag (If you want to pin the version)

    # [Source: Zip] 
    - name: "finance-analyst"
      source: "https://clawhub.ai/download/skills/finance-v1.2.0.zip"

    # [Source: NPM] 
    - name: "google-search"
      source: "npm:@modelcontextprotocol/server-google-search"

    # [Source: PyPI] 
    - name: "local-time"
      source: "pip:mcp-server-time"
  
  # --------------------------------------------------------------
  # Environment Mode
  # --------------------------------------------------------------
   # "standard": Lightweight Python environment. Fast boot time.
   # "full": Heavy environment including Chrome, FFmpeg, Node.js and OpenClaw. REQUIRED if you use skills or Browser automation.
  mode: "standard"

  # --------------------------------------------------------------
  # Execution Mode
  # --------------------------------------------------------------
   # "serverless": 
   # "interactive":
   # "daemon": 24/7 Always-on. Ideal for monitoring or long-running services.
  lifecycle: "serverless"

# ------------------------------------------------------------------
# 4. Authentication
# ------------------------------------------------------------------
# Declare if your agent needs user's OAuth tokens.
# NOTE: Use the official scope strings defined by the provider.
auth:
  providers:
    # [OAuth: Google]
    - name: "google"
      scopes: 
        - "https://www.googleapis.com/auth/calendar.readonly"
        - "https://www.googleapis.com/auth/gmail.send"

    # [OAuth: GitHub]
    - name: "github"
      scopes: 
        - "repo"
        - "read:user"

# ------------------------------------------------------------------
# 5. Governance (Policies)
# ------------------------------------------------------------------
policies:
  allow_internet_access: true
  max_steps: 20
  # Optional: Override serverless run timeout for this agent (seconds).
  # execution_timeout_seconds: 600
  ```

### Field Reference Table

|Section|Field|Type|Description|
|--------|-----------|--------------------------|-------------------------|
| Persona   | name | String|Public display name of the agent.  |
|  |  version  | String |The semantic version of the agent (e.g., 1.0.0). |
|  |  description  | String |Short tagline for search results and cards. |
|  |  assets.icon   | URL|512x512px PNG/JPG image.|
| Interface  | input| Schema|Standard JSON Schema defining user inputs.  |
|  |  x-ui-widget | UI Hint| Values: textarea, password, color, file.|
|Runtime| adapter.type| Enum |crewai, langchain,langgraph, custom, node, openclaw.|
| |entry_point| String| Python path (module:obj) OR Shell command (e.g. "npm start").|
| |environment_variables |List |Names of required env vars (e.g., OPENAI_API_KEY).|
| |skills |List |List of MCP Skills to mount.|
| |mode |Enum |standard (Default), full. Selects the container environment.|
| Auth|providers |List |List of OAuth providers.|
|Policies| max_steps |Integer |Maximum execution steps to prevent infinite loops.|
