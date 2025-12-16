from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseAdapter(ABC):
    
    def __init__(self, agent_instance: Any):
        self.agent = agent_instance
        self._pending_inputs: Dict[str, Any] = {}

    @abstractmethod
    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def set_tools(self, tools: List[Any]) -> None:
        pass