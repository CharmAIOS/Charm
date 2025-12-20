from typing import Any, Dict, List
import inspect
import asyncio
from .base import BaseAdapter
from ..core.logger import logger

class CharmCrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Framework."""

    def _ensure_instantiated(self):
        self._smart_instantiate()

        if not hasattr(self.agent, "kickoff"):
            if hasattr(self.agent, "crew") and hasattr(self.agent.crew, "kickoff"):
                print("[Charm] Detected Crew Wrapper. Switching to inner '.crew' attribute.")
                self.agent = self.agent.crew

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()

        if not hasattr(self.agent, "kickoff"):
             return {
                 "status": "error", 
                 "error_type": "CharmExecutionError",
                 "message": f"Entry point did not resolve to a CrewAI object. Got {type(self.agent).__name__} instead."
             }

        native_input = inputs
        if "input" in inputs and "topic" not in inputs:
            native_input = {"topic": inputs["input"], **inputs}

        result = None
        try:
            result = self.agent.kickoff(inputs=native_input)
        
        except Exception as e:
            error_msg = str(e).lower()
            if "await" in error_msg or "async" in error_msg or "coroutine" in error_msg:
                logger.info("[Charm] Detected Async Crew requirements. Switching to async execution...")
                
                if hasattr(self.agent, "akickoff"): 
                    result = self._execute_async_safely(self.agent.akickoff(inputs=native_input))
                elif hasattr(self.agent, "kickoff_async"): #
                    result = self._execute_async_safely(self.agent.kickoff_async(inputs=native_input))
                else:
                    return {"status": "error", "message": f"Async required but no async method found: {e}"}
            else:
                return {"status": "error", "message": str(e)}

        try:
            output_str = ""
            if hasattr(result, "raw"):
                output_str = result.raw
            else:
                output_str = str(result)

            return {"status": "success", "output": output_str}
        except Exception as e:
             return {"status": "error", "message": f"Output parsing error: {e}"}

    def get_state(self) -> Dict[str, Any]:
        self._ensure_instantiated()
        if hasattr(self.agent, "agents"):
            return {
                "agents": [a.role for a in self.agent.agents],
                "tasks_count": len(self.agent.tasks)
            }
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        self._ensure_instantiated()
        if hasattr(self.agent, "agents"):
            for agent in self.agent.agents:
                if not hasattr(agent, "tools"):
                    agent.tools = []
                agent.tools.extend(tools)