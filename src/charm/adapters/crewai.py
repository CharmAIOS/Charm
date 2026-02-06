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

    def _build_context_block(self, user_profile: str, history: List[Dict[str, str]]) -> str:
        """
        Constructs a clean Markdown block containing Profile and History.
        """
        sections = []

        # 1. Global Memory (Profile)
        if user_profile:
            sections.append(f"## User Profile & Preferences\n{user_profile}")

        # 2. Short-term Memory (History)
        if history:
            recent_history = history[-10:]
            hist_text = "## Recent Conversation Context\n"
            for msg in recent_history:
                role = msg.get("role", "unknown").upper()
                content = str(msg.get("content", "")).strip()
                if content:
                    hist_text += f"- **{role}**: {content}\n"

            sections.append(hist_text)

        if not sections:
            return ""

        return "\n\n".join(sections) + "\n\n## Current Task Instruction\n"

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

        # Extract system keys
        _ = native_input.pop("__charm_state__", None)
        history_data = native_input.pop("__charm_history__", None)
        user_profile = self._get_user_profile()

        context_block = self._build_context_block(user_profile, history_data)

        if context_block and hasattr(self.agent, "tasks") and self.agent.tasks:
            try:
                first_task = self.agent.tasks[0]
                if (
                    "## User Profile" not in first_task.description
                    and "## Recent Conversation" not in first_task.description
                ):
                    original_desc = first_task.description
                    first_task.description = context_block + original_desc
                    logger.debug(
                        f"[Charm] Injected global context into CrewAI Task: {first_task.description[:50]}..."
                    )
            except Exception as e:
                logger.warning(f"[Charm] Failed to inject context into task: {e}")

        # Handle simple string input case
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
