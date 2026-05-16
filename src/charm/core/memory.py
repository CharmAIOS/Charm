from typing import Dict, List
import warnings

from .storage import StorageManager

def load_memory_snapshot() -> List[Dict[str, str]]:
    """
    [DEPRECATED] Hydrates conversation history from the injected memory file.
    Please use `StorageManager.get_provider(config).load_messages(thread_id)` instead.
    """
    warnings.warn(
        "load_memory_snapshot is deprecated. Use StorageManager instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # Use the default local provider, assuming empty thread_id for legacy behavior
    provider = StorageManager.get_provider("local", {})
    return provider.load_messages("default_thread")
