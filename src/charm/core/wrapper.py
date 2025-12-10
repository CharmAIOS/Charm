from typing import Any, Dict, List, Optional
from ..adapters.base import BaseAdapter
from .errors import CharmExecutionError
from .logger import logger

class CharmWrapper:
    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Invoking agent via CharmWrapper...")
        try:
            return self.adapter.invoke(inputs)
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")

            return {
                "status": "error",
                "error_type": "CharmExecutionError",
                "message": str(e)
            }

    def get_state(self) -> Dict[str, Any]:
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        self.adapter.set_tools(tools)