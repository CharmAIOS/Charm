## Configuration Guide: The UAC Manifest

### Getting Started
Depending on your project status, choose the path that fits you best.

Path A: used init
If you want a standardized setup:

```bash
charm init my-agent
cd my-agent
```
Path B: created the file manually

1. Create a file named charm.yaml in your project root.

> The charm.yaml file must always be at the root level of your project

```plaintext

my-agent/             <-- Project Root
├── charm.yaml        <-- The Manifest
├── pyproject.toml    <-- dependencies
└── src/
    └── main.py       <-- Your Agent Logic
```
2. Copy the Annotated Reference below into it.

3. Update the entry_point field to point to your existing agent object.
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
  name: "Research Assistant"       # Display Name (Max 50 chars)
  
  # [Agent] Your Agent's Semantic Version. Update this when publishing updates.
  version: "0.1.0"                 
  
  description: "Deep research on any topic."  # Tagline (Card view, Max 100 chars)
  
  # Full description supports Markdown. Used for the Info Page.
  full_description: |
    # Research Assistant
    This agent uses advanced search tools to aggregate information.
    
    ## Capabilities
    - Web Search
    - Summarization
    - Market Analysis
    
  authors: ["Brand, Company, or Individual Name"]
  tags: ["research", "productivity"]
  license: "MIT"
  
  # Assets for the Storefront
  assets:
    icon: "https://your-site.com/assets/icon.png"      # 512x512 Square
    banner: "https://your-site.com/assets/banner.png"  # 1200x600 Wide

pricing:
  type: "free"  # Options: free, usage_based, one_time

# ------------------------------------------------------------------
# 2. Interface (UI Generation)
# ------------------------------------------------------------------
# This section auto-generates the Input Form on Charm Cloud.
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
      
      # Example 3: File Upload (Auto-Injection)
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
# 3. Runtime (Execution Logic)
# ------------------------------------------------------------------
runtime:
  adapter:
    type: "crewai" # Options: crewai, langchain, langgraph, custom
    
    # --------------------------------------------------------------
    # ENTRY POINT: Where is your agent object?
    # Format: <python_module_path>:<variable_or_function_name>
    # --------------------------------------------------------------
    # [Case A] For Frameworks (CrewAI, LangChain): Point to the agent instance.
    # entry_point: "src.main:my_crew"
    
    # [Case B] For Custom (Pure Python): Point to a function or class instance.
    # It must accept a dictionary and return a dictionary (or string).
    entry_point: "src.my_script:run_pipeline"
    
    # --------------------------------------------------------------
    # SECURE ENV VARS: List keys your agent needs.
    # DO NOT put values here. The Runner injects them securely.
    # --------------------------------------------------------------
    environment_variables:
      - "OPENAI_API_KEY"
      - "SERPER_API_KEY"

  # (Advanced) Dependency Injection from Charm System
  injections:
    llm_client: true  # Inject standard LLM client?
    tools: []         # Inject other agents as tools (by Slug)

# ------------------------------------------------------------------
# 4. Governance (Policies)
# ------------------------------------------------------------------
policies:
  allow_internet_access: true
  max_steps: 20
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
|Runtime|	adapter.type|	Enum	|crewai, langchain,langgraph, custom.|
| |entry_point|	String|	Python path (module:obj). For custom, can be a function or object with invoke().|
| |environment_variables	|List	|Names of required env vars (e.g., OPENAI_API_KEY).|
|Policies|	max_steps	|Integer	|Maximum execution steps to prevent infinite loops.|