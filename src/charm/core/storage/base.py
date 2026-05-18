from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseMemoryStore(ABC):
    """
    Abstract Base Class for Charm Memory Plugins.
    Community developers can inherit this to create integrations with Redis, Postgres, etc.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def load_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        """Load conversation history for a given thread."""
        pass

    @abstractmethod
    def save_messages(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        """Save conversation history for a given thread."""
        pass

    def get_langgraph_checkpointer(self) -> Any:
        """
        Return a LangGraph BaseCheckpointSaver if supported.
        Return None if this storage backend doesn't support LangGraph Checkpointing.
        """
        return None
