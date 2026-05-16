import sys
from typing import Any, Dict, Optional

from .base import BaseMemoryStore
from ..logger import logger

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


class StorageManager:
    """Manages the discovery and instantiation of Memory Storage plugins."""

    _instance: Optional[BaseMemoryStore] = None

    @classmethod
    def get_provider(cls, provider_name: str, config: Dict[str, Any]) -> BaseMemoryStore:
        """
        Loads the configured memory provider via entry points.
        Caches the instance so subsequent calls return the same connection pool.
        """
        if cls._instance is not None:
            return cls._instance

        # Built-in providers
        if not provider_name or provider_name == "local":
            from .local import LocalFileMemory
            cls._instance = LocalFileMemory(config)
            return cls._instance
            
        if provider_name == "supabase":
            from .supabase import SupabaseMemory
            cls._instance = SupabaseMemory(config)
            return cls._instance

        # Load from entry_points (charm.memory)
        eps = entry_points(group="charm.memory")
        for ep in eps:
            if ep.name == provider_name:
                try:
                    plugin_class = ep.load()
                    if not issubclass(plugin_class, BaseMemoryStore):
                        logger.error(f"Plugin '{provider_name}' does not inherit from BaseMemoryStore.")
                        break
                    cls._instance = plugin_class(config)
                    logger.info(f"💾 Storage Provider loaded: {provider_name}")
                    return cls._instance
                except Exception as e:
                    logger.error(f"Failed to load memory plugin '{provider_name}': {e}")
                    break
        
        logger.warning(f"Memory plugin '{provider_name}' not found. Falling back to local storage.")
        from .local import LocalFileMemory
        cls._instance = LocalFileMemory(config)
        return cls._instance
