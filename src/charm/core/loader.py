import os

import yaml  # type: ignore

from ..adapters.base import BaseAdapter
from ..adapters.crewai import CharmCrewAIAdapter
from ..adapters.custom import CharmCustomAdapter
from ..adapters.langchain import CharmLangChainAdapter
from ..adapters.langgraph import CharmLangGraphAdapter
from ..contracts.uac import CharmConfig
from .errors import CharmConfigError, CharmValidationError
from .logger import logger
from .utils import dynamic_import
from .wrapper import CharmWrapper


class CharmLoader:
    """Responsible for bootstrapping the agent from the file system."""

    @staticmethod
    def load(project_path: str) -> CharmWrapper:
        logger.info(f"Loading Charm project from: {project_path}")

        # 1. Load Configuration
        yaml_path = os.path.join(project_path, "charm.yaml")
        if not os.path.exists(yaml_path):
            raise CharmConfigError(f"Missing charm.yaml in {project_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            # Validate against UAC Pydantic model
            config = CharmConfig(**raw_data)
        except Exception as e:
            raise CharmValidationError(f"Invalid charm.yaml: {e}") from e

        # 2. Dynamic Import of User Code
        agent_instance = dynamic_import(config.runtime.adapter.entry_point, project_path)

        # 3. Adapter Selection
        adapter_type = config.runtime.adapter.type
        logger.debug(f"Detected adapter: {adapter_type}")

        adapter: BaseAdapter
        if adapter_type == "crewai":
            adapter = CharmCrewAIAdapter(agent_instance)
        elif adapter_type == "langchain":
            adapter = CharmLangChainAdapter(agent_instance)
        elif adapter_type == "langgraph":
            adapter = CharmLangGraphAdapter(agent_instance)
        elif adapter_type == "custom":
            adapter = CharmCustomAdapter(agent_instance)
        else:
            raise CharmValidationError(f"Unsupported adapter type: {adapter_type}")

        # 4. Return the standardized wrapper
        return CharmWrapper(adapter=adapter, config=config)
