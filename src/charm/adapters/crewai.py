from typing import Any, Dict, List, Optional

from ..core.logger import logger
from .base import BaseAdapter


class CharmCrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Framework."""

    def _ensure_instantiated(self):
        self._smart_instantiate()
        if not hasattr(self.agent, "kickoff"):
            if hasattr(self.agent, "crew") and hasattr(self.agent.crew, "kickoff"):
                print("[Charm] Detected Crew Wrapper. Switching to inner '.crew' attribute.")
                self.agent = self.agent.crew

    def _inject_callbacks(self, callbacks: List[Any]):
        if not callbacks:
            return
        if hasattr(self.agent, "agents"):
            for agent in self.agent.agents:
                if hasattr(agent, "callbacks"):
                    if agent.callbacks is None:
                        agent.callbacks = []
                    agent.callbacks.extend(callbacks)
                if hasattr(agent, "llm"):
                    if hasattr(agent.llm, "callbacks"):
                        if agent.llm.callbacks is None:
                            agent.llm.callbacks = []
                        agent.llm.callbacks.extend(callbacks)

    def _format_history_as_context(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return ""
        text = "\n\n--- Conversation History ---\n"
        for msg in history:
            role = msg.get("role", "unknown").upper()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue

            text += f"{role}: {content}\n"
        text += "--- End of History ---\n\n"
        return text

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        self._pending_inputs = inputs

        try:
            self._ensure_instantiated()
        except Exception as e:
            return {
                "status": "error",
                "error_type": "InstantiationError",
                "message": f"Failed to instantiate CrewAI agent: {str(e)}",
            }

        if not hasattr(self.agent, "kickoff"):
            return {
                "status": "error",
                "error_type": "ContractViolation",
                "message": (
                    f"Entry point resolved to type '{type(self.agent).__name__}', "
                    "but 'crewai' adapter expects a Crew object (missing 'kickoff' method).\n"
                    "Did you select the wrong adapter type in charm.yaml?"
                ),
            }

        if callbacks:
            self._inject_callbacks(callbacks)

        native_input = inputs.copy()

        _ = native_input.pop("__charm_state__", None)

        history_data = native_input.pop("__charm_history__", None)

        # Advanced Context Injection for CrewAI
        if history_data:
            # Append to input string
            history_str = self._format_history_as_context(history_data)
            if "topic" in native_input and isinstance(native_input["topic"], str):
                native_input["topic"] += history_str
            elif "input" in native_input and isinstance(native_input["input"], str):
                native_input["input"] += history_str

            # Inject structured context into the first Task
            if hasattr(self.agent, "tasks") and self.agent.tasks:
                context_summary = "\n\n### Context from Previous Turns:\n"
                for msg in history_data[-6:]:
                    role = msg.get("role", "user").upper()
                    content = msg.get("content", "")
                    context_summary += f"- **{role}**: {content}\n"

                context_summary += (
                    "\nBased on the above context, continue with the current task goal.\n"
                )

                try:
                    first_task = self.agent.tasks[0]
                    if "### Context" not in first_task.description:
                        first_task.description = context_summary + first_task.description
                        logger.debug("[Charm] Injected history context into CrewAI Task #1")
                except Exception as e:
                    logger.warning(f"[Charm] Failed to inject context into task: {e}")

        if isinstance(native_input, str):
            native_input = {"topic": native_input}

        result = None
        try:
            result = self.agent.kickoff(inputs=native_input)

        except Exception as e:
            error_msg = str(e).lower()
            if "await" in error_msg or "async" in error_msg or "coroutine" in error_msg:
                logger.info(
                    "[Charm] Detected Async Crew requirements. Switching to async execution..."
                )
                if hasattr(self.agent, "akickoff"):
                    result = self._execute_async_safely(self.agent.akickoff(inputs=native_input))
                elif hasattr(self.agent, "kickoff_async"):
                    result = self._execute_async_safely(
                        self.agent.kickoff_async(inputs=native_input)
                    )
                else:
                    return {
                        "status": "error",
                        "message": f"Async required but no async method found: {e}",
                    }
            else:
                return {"status": "error", "message": str(e)}

        try:
            output_str = ""
            if hasattr(result, "raw"):
                output_str = result.raw
            else:
                output_str = str(result)

            return {"status": "success", "output": output_str, "charm_state": ""}
        except Exception as e:
            return {"status": "error", "message": f"Output parsing error: {e}"}

    def set_tools(self, tools: List[Any]) -> None:
        pass
