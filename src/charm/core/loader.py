import os
import yaml
from ..contracts.uac import CharmConfig
from ..adapters.crewai import CharmCrewAIAdapter
from ..adapters.langchain import CharmLangChainAdapter
from ..adapters.langgraph import CharmLangGraphAdapter 
from ..adapters.custom import CharmCustomAdapter 

from .wrapper import CharmWrapper
from .errors import CharmConfigError, CharmValidationError
from .utils import dynamic_import
from .logger import logger

class CharmLoader:
    
    @staticmethod
    def load(project_path: str) -> CharmWrapper:
        logger.info(f"Loading Charm project from: {project_path}")
        
        yaml_path = os.path.join(project_path, "charm.yaml")
        if not os.path.exists(yaml_path):
            raise CharmConfigError(f"Missing charm.yaml in {project_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            config = CharmConfig(**raw_data)
        except Exception as e:
            raise CharmValidationError(f"Invalid charm.yaml: {e}")
        
        agent_instance = dynamic_import(config.runtime.adapter.entry_point, project_path)

        adapter_type = config.runtime.adapter.type
        logger.debug(f"Detected adapter: {adapter_type}")

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

        return CharmWrapper(adapter=adapter, config=config)