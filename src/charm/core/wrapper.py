import sys
from typing import Any, Dict, List, Optional, Generator
from ..adapters.base import BaseAdapter
from .errors import CharmExecutionError
from .logger import logger
from .io import CharmEmitter, StdoutInterceptor
from .callbacks import CharmCallbackHandler
from .memory import load_memory_snapshot 

class CharmWrapper:
    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def _inject_memory(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        history = load_memory_snapshot()
        if history:
            new_inputs = inputs.copy()
            new_inputs["__charm_history__"] = history
            return new_inputs
        return inputs

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        CharmEmitter.emit_status("Initializing Agent Runtime...")
        
        inputs_with_memory = self._inject_memory(inputs)

        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()
        
        stream_state = {"has_streamed": False}
        charm_callback = CharmCallbackHandler(shared_state=stream_state)
        
        try:
            result = self.adapter.invoke(inputs_with_memory, callbacks=[charm_callback])
            
            if result.get("status") == "success":
                if not stream_state.get("has_streamed", False):
                    CharmEmitter.emit_final(result.get("output", ""))
                return result
            else:
                error_msg = result.get("message", "Unknown error")
                CharmEmitter.emit_error(error_msg)
                sys.exit(0) 
                return result
                
        except Exception as e:
            CharmEmitter.emit_error(str(e))
            sys.exit(0)
            return {
                "status": "error", 
                "error_type": "CharmExecutionError",
                "message": str(e)
            }
        finally:
            sys.stdout = original_stdout

    def get_state(self) -> Dict[str, Any]:
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        self.adapter.set_tools(tools)