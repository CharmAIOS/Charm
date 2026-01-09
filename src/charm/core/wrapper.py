import sys
from typing import Any, Dict, List, Optional

from ..adapters.base import BaseAdapter
from .callbacks import CharmCallbackHandler
from .io import CharmEmitter, StdoutInterceptor
from .logger import logger
from .memory import load_memory_snapshot


class CharmWrapper:
    """
    The runtime container that orchestrates the execution lifecycle.
    """

    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def _inject_memory(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Loads conversation history from disk and injects it into inputs.
        """
        # Handle None or non-dict inputs gracefully
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            logger.warning(f"[Charm] Input is not a dict: {type(inputs)}. Wrapping in 'input'.")
            inputs = {"input": inputs}

        history = load_memory_snapshot()
        if history:
            new_inputs = inputs.copy()
            new_inputs["__charm_history__"] = history
            return new_inputs
        return inputs

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution entry point. Handles I/O interception, memory, and error handling.
        """
        CharmEmitter.emit_status("Initializing Agent Runtime...")

        # Memory Injection
        inputs_with_memory = self._inject_memory(inputs)

        # Log the keys being passed to the adapter
        debug_keys = [k for k in inputs_with_memory.keys() if k != "__charm_history__"]
        logger.debug(f"[Charm] Invoking Adapter with keys: {debug_keys}")

        # Hijack Stdout
        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()

        # Track streaming state to avoid double-printing final output
        stream_state = {"has_streamed": False}
        charm_callback = CharmCallbackHandler(shared_state=stream_state)

        try:
            # Execute via Adapter
            result = self.adapter.invoke(inputs_with_memory, callbacks=[charm_callback])

            # State Broadcasting
            if "charm_state" in result and result["charm_state"]:
                CharmEmitter._write("state_update", {"content": result["charm_state"]})

            if result.get("status") == "success":
                # Emit final result only if it wasn't already streamed token-by-token
                if not stream_state.get("has_streamed", False):
                    CharmEmitter.emit_final(result.get("output", ""))
                return result
            else:
                # Handle logical errors from the agent
                error_msg = result.get("message", "Unknown error")
                CharmEmitter.emit_error(error_msg)
                sys.exit(0)  # Exit gracefully for the runner
                return result

        except Exception as e:
            # Global Error Handler
            CharmEmitter.emit_error(str(e))
            sys.exit(0)
            return {"status": "error", "error_type": "CharmExecutionError", "message": str(e)}
        finally:
            # Restore Stdout
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
