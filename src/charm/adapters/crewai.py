from typing import Any, Dict, List
import inspect
from .base import BaseAdapter

class CharmCrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Framework."""

    def _ensure_instantiated(self):
        if callable(self.agent) and not hasattr(self.agent, "kickoff"):
            try:
                print(f"[Charm] Entry point is a callable ({type(self.agent).__name__}), instantiating Crew object...")
                
                sig = inspect.signature(self.agent)
                params = sig.parameters
                
                if len(params) > 0:
                    self.agent = self.agent(self._pending_inputs)
                else:
                    self.agent = self.agent()

            except Exception as e:
                print(f"[Charm] Warning: Failed to instantiate factory function: {e}")

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

        try:
            result = self.agent.kickoff(inputs=native_input)

            output_str = ""
            if hasattr(result, "raw"):
                output_str = result.raw
            else:
                output_str = str(result)

            return {"status": "success", "output": output_str}
        except Exception as e:
            return {"status": "error", "message": str(e)}

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