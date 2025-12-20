from typing import Any, Dict, List
import inspect
import asyncio
from .base import BaseAdapter
from ..core.logger import logger

class CharmLangChainAdapter(BaseAdapter):
    """Adapter for standard LangChain Chains/Agents."""

    def _ensure_instantiated(self):
        self._smart_instantiate()

        if not hasattr(self.agent, "invoke"):
            for attr in ["chain", "agent", "runnable", "pipeline"]:
                if hasattr(self.agent, attr):
                    candidate = getattr(self.agent, attr)
                    if hasattr(candidate, "invoke"):
                        print(f"[Charm] Detected LangChain Wrapper. Switching to inner '.{attr}' attribute.")
                        self.agent = candidate
                        break

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()
        
        native_input = inputs
        result = None
        
        try:
            result = self.agent.invoke(native_input)
        except Exception as e:
            if hasattr(self.agent, "ainvoke"):
                logger.info("[Charm] Sync invoke failed, attempting Async ainvoke...")
                try:
                    result = self._execute_async_safely(self.agent.ainvoke(native_input))
                except Exception as async_e:
                    return {"status": "error", "message": f"Async execution also failed: {async_e}"}
            else:
                return {"status": "error", "message": str(e)}

        try:
            output_str = str(result)
            
            if isinstance(result, dict):
                for key in ["output", "text", "result", "generation"]:
                    if key in result:
                        val = result[key]
                        if hasattr(val, "text"): 
                            output_str = val.text
                        else:
                            output_str = str(val)
                        break
            
            elif isinstance(result, str):
                output_str = result
            
            elif hasattr(result, "content"):
                output_str = str(result.content)
                
            return {"status": "success", "output": output_str}
        except Exception as e:
            return {"status": "error", "message": f"Output parsing error: {str(e)}"}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        self._ensure_instantiated()
        if hasattr(self.agent, "tools") and isinstance(self.agent.tools, list):
            self.agent.tools.extend(tools)