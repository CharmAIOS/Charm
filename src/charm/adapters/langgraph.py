from typing import Any, Dict, List
import inspect
import asyncio 
from .base import BaseAdapter
from ..core.logger import logger

class CharmLangGraphAdapter(BaseAdapter):
    """Adapter for LangGraph CompiledGraphs."""

    def _ensure_instantiated(self):
        self._smart_instantiate()

        if not hasattr(self.agent, "invoke"):
            if hasattr(self.agent, "app") and hasattr(self.agent.app, "invoke"):
                print("[Charm] Detected Wrapper Class. Switching to inner '.app' attribute.")
                self.agent = self.agent.app
            elif hasattr(self.agent, "graph") and hasattr(self.agent.graph, "invoke"):
                print("[Charm] Detected Wrapper Class. Switching to inner '.graph' attribute.")
                self.agent = self.agent.graph

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()

        config = {"configurable": {"thread_id": "charm_default_thread"}}
        result = None

        try:
            result = self.agent.invoke(inputs, config=config)

        except Exception as e:
            error_str = str(e).lower()
            if "no synchronous function" in error_str or "async" in error_str:
                logger.info("[Charm] Detected Async Graph. Switching to ainvoke...")
                try:
                    result = self._execute_async_safely(self.agent.ainvoke(inputs, config=config))
                except Exception as async_e:
                    return {"status": "error", "message": f"Async Graph Execution Failed: {str(async_e)}"}
            else:
                return {"status": "error", "message": f"Graph Execution Failed: {str(e)}"}

        try:
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
            return {"status": "error", "message": f"Output Processing Error: {str(e)}"}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass