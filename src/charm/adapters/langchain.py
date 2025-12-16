from typing import Any, Dict, List
from .base import BaseAdapter

class CharmLangChainAdapter(BaseAdapter):

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        native_input = inputs
        
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

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        if hasattr(self.agent, "tools") and isinstance(self.agent.tools, list):
            self.agent.tools.extend(tools)