from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class StoreAssets(BaseModel):
    """Visual assets for the Storefront."""

    icon: Optional[str] = Field(None, description="URL to square icon (512x512)")
    banner: Optional[str] = Field(None, description="URL to wide banner image")
    screenshots: List[str] = Field(default_factory=list, description="List of screenshot URLs")


class Persona(BaseModel):
    """Identity and metadata for Store display and Search."""

    name: str = Field(..., description="The public name of the agent shown in the store")
    version: str = Field(
        "0.1.0", pattern=r"^\d+\.\d+\.\d+$", description="Semantic version (e.g. 1.0.0)"
    )
    description: str = Field(..., description="Short tagline for card view (max 100 chars)")
    full_description: Optional[str] = Field(
        None, description="Long markdown description for the detail page"
    )
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    license: str = Field("Free", description="Usage license (e.g. 'Proprietary', 'MIT')")
    assets: Optional[StoreAssets] = None


class TrialConfig(BaseModel):
    enabled: bool = False
    days: Optional[int] = Field(None, ge=1)


class Pricing(BaseModel):
    """Commercial model for the Charm Store."""

    model: Literal["free", "subscription", "one_time"] = Field("free")
    amount: float = Field(0.0, description="Price in USD")
    billing_period: Optional[Literal["monthly", "annual"]] = None
    trial: Optional[TrialConfig] = None


class InterfaceState(BaseModel):
    """Schema of the persistent state."""

    format: Literal["json", "binary", "pydantic_model"] = "json"
    schema_: Dict[str, Any] = Field(
        default_factory=dict, alias="schema", description="Structure of the state object"
    )


class InterfaceConfig(BaseModel):
    """Defines Inputs, Outputs, and State structure."""

    input: Dict[str, Any] = Field(..., description="JSON Schema for input parameters")
    output: Dict[str, Any] = Field(..., description="JSON Schema for output format")
    state: Optional[InterfaceState] = None
    ui: Optional[Dict[str, Any]] = Field(
        None, description="UI schema for dynamic form rendering"
    )


# Skill Configuration
class SkillConfig(BaseModel):
    """Configuration for an external Skill/MCP Server."""

    name: str = Field(..., description="Unique identifier for the skill (e.g. 'google-search')")
    source: str = Field(
        ...,
        description="Source: 'smithery:@org/pkg', 'git:https://...', 'pip:package', or 'local:./path'",
    )
    version: Optional[str] = Field(None, description="Specific version or commit hash")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Environment variables or config overrides for this skill"
    )


# -----------------------------------------------------------------------------
# [NEW] OpenClaw Specific Configuration
# -----------------------------------------------------------------------------
class OpenClawConfig(BaseModel):
    """
    Configuration specific to the OpenClaw runtime engine.
    """

    system_prompt: Optional[str] = Field(
        None,
        description="The core personality or instruction set for the agent (writes to IDENTITY.md).",
    )
    model: str = Field(
        "gpt-4o", description="The LLM model ID to use (e.g. gpt-4o, claude-3-5-sonnet)."
    )
    temperature: float = Field(0.0, description="LLM sampling temperature.")

    auto_install_dependencies: bool = Field(
        True,
        description="If True, recursively installs requirements.txt/package.json found in local skills.",
    )


# Keys that belong to the LLM/model layer — never treated as tool keys
# regardless of whether the UAC uses the legacy flat-list format.
_KNOWN_MODEL_KEYS: frozenset[str] = frozenset({
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_API_HOST",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVEAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
    "CHARM_LLM_PROXY_BASE",
    "CHARM_LLM_PROXY_KEY",
})


class EnvVars(BaseModel):
    """Environment variables split logically to support backend validation flows."""

    models: List[str] = Field(default_factory=list, description="LLM/Model API keys")
    tools: List[str] = Field(default_factory=list, description="Tool/Skill API keys")


class MemoryConfig(BaseModel):
    """Configuration for the state/memory storage plugin."""

    provider: str = Field(
        default="local",
        description="The memory provider plugin name (e.g., 'local', 'redis', 'postgres').",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration (e.g., connection URLs).",
    )


class RuntimeAdapter(BaseModel):
    """Instructs the Loader how to bootstrap this agent."""

    type: str = Field(
        ..., description="The specific SDK adapter to use"
    )
    entry_point: Optional[str] = Field(
        None,
        description="Python import path (src.main:app) OR Shell command. Optional for 'openclaw'.",
    )
    environment_variables: EnvVars = Field(
        default_factory=EnvVars, description="Required env vars to be injected"
    )

    @field_validator("environment_variables", mode="before")
    @classmethod
    def convert_legacy_env_list_to_tools(cls, v):
        if isinstance(v, list):
            # Legacy flat list: classify each key into models vs tools so that
            # LLM provisioning keys are never passed to the tool-key interceptor.
            return {
                "models": [k for k in v if k in _KNOWN_MODEL_KEYS],
                "tools": [k for k in v if k not in _KNOWN_MODEL_KEYS],
            }
        return v


class RuntimeConfig(BaseModel):
    adapter: RuntimeAdapter

    # List of Skills to mount (For OpenClaw/MCP)
    skills: List[SkillConfig] = Field(
        default_factory=list, description="List of MCP Skills to mount."
    )

    telemetry: List[str] = Field(
        default_factory=list, description="List of telemetry exporter names to enable."
    )

    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Configuration for persistent memory and state storage.",
    )

    # Add the config field here
    config: Optional[OpenClawConfig] = Field(
        None, description="Engine-specific configuration (e.g. for OpenClaw)."
    )

    custom_image: Optional[str] = Field(
        None, description="Custom Docker image URI for the runtime environment."
    )

    mode: Literal["standard", "full"] = Field(
        "standard",
        description="Select 'full' if you need Browser(Chrome), FFmpeg, or Node.js runtime. (Deprecated)",
    )

    lifecycle: Literal["serverless", "daemon", "interactive"] = Field(
        "serverless",
        description="Execution mode: 'serverless' (max 10 mins), 'daemon' (24/7 always-on), or 'interactive' (real-time streaming).",
    )


class HumanInTheLoop(BaseModel):
    """Configuration for human oversight."""

    enabled: bool = False
    triggers: List[str] = Field(
        default_factory=list, description="Keywords or tool names that trigger approval"
    )


class Policies(BaseModel):
    """Governance and safety rules."""

    allow_internet_access: bool = True
    human_in_the_loop: Optional[HumanInTheLoop] = None
    max_steps: int = Field(20, description="Max execution steps")
    budget_limit: float = Field(0.0, description="Max USD cost per run")
    execution_timeout_seconds: Optional[int] = Field(
        None,
        ge=1,
        description="Optional serverless execution timeout override in seconds.",
    )


# Auth Configuration
class AuthProvider(BaseModel):
    """Configuration for OAuth requirements."""

    name: str = Field(..., description="Provider name (e.g. 'google', 'github', 'twitter')")
    scopes: List[str] = Field(default_factory=list, description="List of required OAuth scopes")


class AuthConfig(BaseModel):
    """Global authentication requirements for the agent."""

    providers: List[AuthProvider] = Field(default_factory=list)


class CharmConfig(BaseModel):
    version: str = Field(
        ..., pattern=r"^0\.4(\.\d+)?$", description="Contract version (Compatible with 0.4.x SDK)"
    )

    id: Optional[str] = Field(None, description="Unique UUID for the agent. Generated by CLI.")
    persona: Persona
    pricing: Optional[Pricing] = None

    # Global Auth Requirements
    auth: Optional[AuthConfig] = None

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
