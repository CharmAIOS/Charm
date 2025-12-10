from typing import Any, Dict, List
from .base import BaseAdapter

class CharmCrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Framework."""

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:

        native_input = inputs
        if "input" in inputs and "topic" not in inputs:
            native_input = {"topic": inputs["input"], **inputs}

        result = self.agent.kickoff(inputs=native_input)

        output_str = ""
        if hasattr(result, "raw"):
            output_str = result.raw
        else:
            output_str = str(result)

        return {"status": "success", "output": output_str}

    def get_state(self) -> Dict[str, Any]:

        return {
            "agents": [a.role for a in self.agent.agents],
            "tasks_count": len(self.agent.tasks)
        }

    def set_tools(self, tools: List[Any]) -> None:
        for agent in self.agent.agents:
            if not hasattr(agent, "tools"):
                agent.tools = []
            agent.tools.extend(tools)