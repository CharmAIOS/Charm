from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class StoreAssets(BaseModel):
    """Visual assets for the Storefront."""
    icon: Optional[str] = Field(None, description="URL to square icon (512x512)")
    banner: Optional[str] = Field(None, description="URL to wide banner image")
    screenshots: List[str] = Field(default_factory=list, description="List of screenshot URLs")

class Persona(BaseModel):
    """Identity and metadata for Store display and Search."""
    name: str = Field(..., description="The public name of the agent shown in the store")
    version: str = Field("0.1.0", pattern=r"^\d+\.\d+\.\d+$", description="Semantic version (e.g. 1.0.0)")
    description: str = Field(..., description="Short tagline for card view (max 100 chars)")
    full_description: Optional[str] = Field(None, description="Long markdown description for the detail page")
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    license: str = Field("Free", description="Usage license (e.g. 'Proprietary', 'MIT')")
    assets: Optional[StoreAssets] = None

class Pricing(BaseModel):
    """Commercial model for the Charm Store."""
    type: Literal["free", "usage_based", "subscription", "one_time"] = Field("free")
    amount: float = Field(0.0, description="Price value")
    currency: str = Field("USD", description="Currency code")

class InterfaceState(BaseModel):
    """Schema of the persistent state."""
    format: Literal["json", "binary", "pydantic_model"] = "json"
    schema_: Dict[str, Any] = Field(default_factory=dict, alias="schema", description="Structure of the state object")

class InterfaceConfig(BaseModel):
    """Defines Inputs, Outputs, and State structure."""
    input: Dict[str, Any] = Field(..., description="JSON Schema for input parameters")
    output: Dict[str, Any] = Field(..., description="JSON Schema for output format")
    state: Optional[InterfaceState] = None

class RuntimeAdapter(BaseModel):
    """Instructs the Loader how to bootstrap this agent."""
    type: Literal["langchain", "crewai", "langgraph", "custom"] = Field(..., description="The specific SDK adapter to use")
    entry_point: str = Field(..., description="Python import path e.g. 'src.agent:my_crew'")
    environment_variables: List[str] = Field(default_factory=list, description="Required env vars to be injected")

class RuntimeInjections(BaseModel):
    """Resources the agent expects the Runtime to inject."""
    llm_client: bool = Field(False, description="If true, injects a configured LLM client")
    tools: List[str] = Field(default_factory=list, description="List of standard Charm Tools (IDs) to be injected")
    memory_store: bool = Field(False, description="If true, injects a connection to Vector Store")

class RuntimeConfig(BaseModel):
    adapter: RuntimeAdapter
    injections: Optional[RuntimeInjections] = None

class HumanInTheLoop(BaseModel):
    """Configuration for human oversight."""
    enabled: bool = False
    triggers: List[str] = Field(default_factory=list, description="Keywords or tool names that trigger approval")

class Policies(BaseModel):
    """Governance and safety rules."""
    allow_internet_access: bool = True
    human_in_the_loop: Optional[HumanInTheLoop] = None
    max_steps: int = Field(20, description="Max execution steps")
    budget_limit: float = Field(0.0, description="Max USD cost per run")


class CharmConfig(BaseModel):
    version: str = Field(
        ..., 
        pattern=r"^0\.4", 
        description="Contract version (Compatible with 0.4.x SDK)"
    )
    
    persona: Persona
    pricing: Optional[Pricing] = None
    goals: List[str] = Field(default_factory=list, description="Semantic goals for search indexing")
    
    interface: InterfaceConfig
    runtime: RuntimeConfig
    policies: Optional[Policies] = None
    
    workflow: Optional[Dict[str, Any]] = None


def is_compatible(yaml_version: str, sdk_version: str) -> bool:
    try:
        y_parts = yaml_version.split(".")
        s_parts = sdk_version.split(".")
        
        if len(y_parts) < 2 or len(s_parts) < 2:
            return False

        return (y_parts[0] == s_parts[0]) and (y_parts[1] == s_parts[1])
    except Exception:
        return False