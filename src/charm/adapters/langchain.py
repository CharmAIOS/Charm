from typing import Any, Dict, List
import inspect
from .base import BaseAdapter
from ..core.logger import logger

class CharmLangChainAdapter(BaseAdapter):
    """Adapter for standard LangChain Chains/Agents."""

    def _ensure_instantiated(self):
        if callable(self.agent) and not hasattr(self.agent, "invoke"):
            try:
                print(f"[Charm] Instantiating LangChain agent from factory...")
                
                sig = inspect.signature(self.agent)
                if len(sig.parameters) > 0:
                    self.agent = self.agent(self._pending_inputs)
                else:
                    self.agent = self.agent()
                    
            except Exception as e:
                print(f"[Charm] Warning: Failed to instantiate factory: {e}")

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()
        
        native_input = inputs
        
        try:
            result = self.agent.invoke(native_input)

            output_str = str(result)
            
            if isinstance(result, dict):
                for key in ["output", "text", "result"]:
                    if key in result:
                        output_str = str(result[key])
                        break
            
            elif isinstance(result, str):
                output_str = result
                
            return {"status": "success", "output": output_str}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        self._ensure_instantiated()
        if hasattr(self.agent, "tools") and isinstance(self.agent.tools, list):
            self.agent.tools.extend(tools)