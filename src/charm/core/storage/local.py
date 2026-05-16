import json
import os
from typing import Any, Dict, List

from .base import BaseMemoryStore
from ..logger import logger

class LocalFileMemory(BaseMemoryStore):
    """
    Default Local Storage Provider for memory.
    Saves memory as a JSON file locally.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # In cloud environments, CHARM_MEMORY_FILE may be injected by the runner.
        self.injected_file = os.getenv("CHARM_MEMORY_FILE")
        
        self.workspace_dir = os.getenv("CHARM_WORKSPACE_DIR") or os.path.join(os.getcwd(), "workspace")
        self.memory_dir = os.path.join(self.workspace_dir, ".charm", "memory")
        
        if not self.injected_file:
            os.makedirs(self.memory_dir, exist_ok=True)

    def _get_file_path(self, thread_id: str) -> str:
        if self.injected_file:
            return self.injected_file
        return os.path.join(self.memory_dir, f"{thread_id}.json")

    def load_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        path = self._get_file_path(thread_id)
        if not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.error(f"Failed to load local memory snapshot: {e}")
            return []

    def save_messages(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        path = self._get_file_path(thread_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save local memory snapshot: {e}")
