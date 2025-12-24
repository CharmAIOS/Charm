import sys
from typing import Any, Dict, List, Optional, Generator
from ..adapters.base import BaseAdapter
from .errors import CharmExecutionError
from .logger import logger
from .io import CharmEmitter, StdoutInterceptor
from .callbacks import CharmCallbackHandler
from .memory import load_memory_snapshot 

class CharmWrapper:
    """
    The runtime container that orchestrates the execution lifecycle.
    """
    
    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        # The adapter wraps the specific framework (CrewAI, LangChain, etc.)
        self.adapter = adapter
        self.config = config

    def _inject_memory(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Loads conversation history from disk and injects it into inputs.
        """
        history = load_memory_snapshot()
        if history:
            new_inputs = inputs.copy()
            # The key '__charm_history__' is a reserved protocol key used by Adapters.
            new_inputs["__charm_history__"] = history
            return new_inputs
        return inputs

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution entry point. Handles I/O interception, memory, and error handling.
        """
        CharmEmitter.emit_status("Initializing Agent Runtime...")
        
        # 1. Prepare Inputs (Memory Injection)
        inputs_with_memory = self._inject_memory(inputs)

        # 2. Hijack Stdout (To capture print() as events)
        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()
        
        # Track streaming state to avoid double-printing final output
        stream_state = {"has_streamed": False}
        charm_callback = CharmCallbackHandler(shared_state=stream_state)
        
        try:
            # 3. Execute via Adapter
            result = self.adapter.invoke(inputs_with_memory, callbacks=[charm_callback])
            
            if result.get("status") == "success":
                # Emit final result only if it wasn't already streamed token-by-token
                if not stream_state.get("has_streamed", False):
                    CharmEmitter.emit_final(result.get("output", ""))
                return result
            else:
                # Handle logical errors from the agent
                error_msg = result.get("message", "Unknown error")
                CharmEmitter.emit_error(error_msg)
                sys.exit(0) # Exit gracefully for the runner
                return result
                
        except Exception as e:
            # 4. Global Error Handler (Crash protection)
            CharmEmitter.emit_error(str(e))
            sys.exit(0)
            return {
                "status": "error", 
                "error_type": "CharmExecutionError",
                "message": str(e)
            }
        finally:
            # 5. Restore Stdout (Crucial for cleanup)
            sys.stdout = original_stdout

    def get_state(self) -> Dict[str, Any]:
        """Delegate state retrieval to adapter."""
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        """Delegate tool injection."""
        self.adapter.set_tools(tools)