from typing import Any, Dict, List
import inspect
from .base import BaseAdapter

class CharmLangGraphAdapter(BaseAdapter):
    """Adapter for LangGraph CompiledGraphs."""

    def _ensure_instantiated(self):
        if callable(self.agent) and not hasattr(self.agent, "invoke"):
            try:
                print(f"[Charm] Instantiating LangGraph from factory...")
                
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

        config = {"configurable": {"thread_id": "charm_default_thread"}}
        
        try:
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
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass