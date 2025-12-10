from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseAdapter(ABC):
    """
    Abstract Base Class for all Charm Framework Adapters.
    Enforces a consistent interface for invocation and state management.
    """
    
    def __init__(self, agent_instance: Any):
        self.agent = agent_instance

    @abstractmethod
    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standard entry point for execution.
        Must normalize input/output to standard JSON (Dict).
        """
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Retrieve a snapshot of the agent's internal state."""
        pass

    @abstractmethod
    def set_tools(self, tools: List[Any]) -> None:
        """Inject external tools into the agent."""
        pass