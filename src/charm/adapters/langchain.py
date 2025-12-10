from typing import Any, Dict, List
from .base import BaseAdapter

class CharmLangChainAdapter(BaseAdapter):
    """Adapter for LangChain / LangGraph."""

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
       
        native_input = inputs
        
        result = self.agent.invoke(native_input)

        output_str = str(result)
        if isinstance(result, dict):

            for key in ["output", "result", "messages"]:
                if key in result:
                    output_str = str(result[key])
                    break
        
        return {"status": "success", "output": output_str}

    def get_state(self) -> Dict[str, Any]:

        return {}

    def set_tools(self, tools: List[Any]) -> None:

        if hasattr(self.agent, "tools"):
            self.agent.tools.extend(tools)

        pass