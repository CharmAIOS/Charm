import json
import os
from typing import Dict, List

from .logger import logger


def load_memory_snapshot() -> List[Dict[str, str]]:
    """
    Hydrates conversation history from the injected memory file.
    """
    # Environment variable injected by the Cloud Runner
    memory_path = os.getenv("CHARM_MEMORY_FILE")

    if not memory_path:
        logger.debug("No memory file environment variable set.")
        return []

    if not os.path.exists(memory_path):
        logger.debug(f"Memory file not found at: {memory_path}")
        return []

    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                logger.info(f"Hydrated {len(data)} messages from memory.")
                return data
            else:
                logger.warning("Memory file format invalid (expected list).")
                return []
    except Exception as e:
        logger.error(f"Failed to load memory snapshot: {e}")
        return []
