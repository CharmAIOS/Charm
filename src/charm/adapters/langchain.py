from typing import Any, Dict, List, Optional

from ..core.logger import logger
from .base import BaseAdapter


class CharmLangChainAdapter(BaseAdapter):
    """Adapter for standard LangChain Chains/Agents."""

    def _ensure_instantiated(self):
        self._smart_instantiate()
        if not hasattr(self.agent, "invoke"):
            for attr in ["chain", "agent", "runnable", "pipeline"]:
                if hasattr(self.agent, attr):
                    candidate = getattr(self.agent, attr)
                    if hasattr(candidate, "invoke"):
                        print(
                            f"[Charm] Detected LangChain Wrapper. Switching to inner '.{attr}' attribute."
                        )
                        self.agent = candidate
                        break

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
                "message": f"Failed to instantiate LangChain agent: {str(e)}",
            }

        if not hasattr(self.agent, "invoke"):
            return {
                "status": "error",
                "error_type": "ContractViolation",
                "message": (
                    f"Entry point resolved to type '{type(self.agent).__name__}', "
                    "but 'langchain' adapter expects a Runnable/Chain object (missing 'invoke' method)."
                ),
            }

        native_input = inputs.copy()

        # Ensure input is not None
        if "input" in native_input:
            if native_input["input"] is None:
                native_input["input"] = ""

        config = {}
        if callbacks:
            config["callbacks"] = callbacks

        result = None
        try:
            result = self.agent.invoke(native_input, config=config)
        except TypeError:
            result = self.agent.invoke(native_input)
        except Exception as e:
            if hasattr(self.agent, "ainvoke"):
                logger.info("[Charm] Sync invoke failed, attempting Async ainvoke...")
                try:
                    result = self._execute_async_safely(
                        self.agent.ainvoke(native_input, config=config)
                    )
                except Exception as async_e:
                    return {"status": "error", "message": f"Async execution also failed: {async_e}"}
            else:
                return {"status": "error", "message": str(e)}

        try:
            output_str = str(result)
            if isinstance(result, dict):
                for key in ["output", "text", "result", "generation"]:
                    if key in result:
                        val = result[key]
                        if hasattr(val, "text"):
                            output_str = val.text
                        else:
                            output_str = str(val)
                        break
            elif isinstance(result, str):
                output_str = result
            elif hasattr(result, "content"):
                output_str = str(result.content)

            return {"status": "success", "output": output_str}
        except Exception as e:
            return {"status": "error", "message": f"Output parsing error: {str(e)}"}

    def set_tools(self, tools: List[Any]) -> None:
        """Set the tools for the agent."""
        pass
