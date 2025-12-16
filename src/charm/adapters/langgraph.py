from typing import Any, Dict, List
from .base import BaseAdapter

class CharmLangGraphAdapter(BaseAdapter):

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:

        config = {"configurable": {"thread_id": "charm_default_thread"}}
        
        result = self.agent.invoke(inputs, config=config)

        output_str = str(result)

        if isinstance(result, dict):
            if "messages" in result:
                messages = result["messages"]
                if isinstance(messages, list) and len(messages) > 0:
                    last_msg = messages[-1]
                    if hasattr(last_msg, "content"):
                        output_str = str(last_msg.content)
                    else:
                        output_str = str(last_msg)
            
            elif "generation" in result:
                output_str = str(result["generation"])
            elif "result" in result:
                output_str = str(result["result"])

        return {"status": "success", "output": output_str}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass