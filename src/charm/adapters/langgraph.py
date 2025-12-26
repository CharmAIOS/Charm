import base64
import json
from typing import Any, Dict, List, Optional

from ..core.logger import logger
from .base import BaseAdapter

# Import MemorySaver for state checkpointing
try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    MemorySaver = None  # type: ignore

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
except ImportError:
    from langchain.schema import AIMessage, HumanMessage, SystemMessage  # type: ignore


class CharmLangGraphAdapter(BaseAdapter):
    """Adapter for LangGraph CompiledGraphs."""

    def _ensure_instantiated(self):
        self._smart_instantiate()

        # Initialize in-memory checkpointer for state management
        self.checkpointer = MemorySaver() if MemorySaver is not None else None

        if not hasattr(self.agent, "invoke"):
            if hasattr(self.agent, "app") and hasattr(self.agent.app, "invoke"):
                print("[Charm] Detected Wrapper Class. Switching to inner '.app' attribute.")
                self.agent = self.agent.app
            elif hasattr(self.agent, "graph") and hasattr(self.agent.graph, "invoke"):
                print("[Charm] Detected Wrapper Class. Switching to inner '.graph' attribute.")
                self.agent = self.agent.graph

        # Re-compile the graph with the checkpointer to enable time-travel/state restoration
        if hasattr(self.agent, "checkpointer") and self.agent.checkpointer is None:
            pass

    def _convert_history_to_messages(self, history: List[Dict[str, str]]) -> List[Any]:
        lc_messages: List[Any] = []
        for msg in history:
            role = msg.get("role")
            content = str(msg.get("content", "")).strip()

            if not content:
                continue

            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))
        return lc_messages

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
                "message": f"Failed to instantiate LangGraph agent: {str(e)}",
            }

        # CompiledStateGraph
        if not hasattr(self.agent, "invoke"):
            return {
                "status": "error",
                "error_type": "ContractViolation",
                "message": (
                    f"Entry point resolved to type '{type(self.agent).__name__}', "
                    "but 'langgraph' adapter expects a CompiledGraph object (missing 'invoke' method).\n"
                    "Did you forget to call `.compile()` on your graph?"
                ),
            }

        # Use a fixed thread ID for the stateless run (state is hydrated manually)
        config: Dict[str, Any] = {"configurable": {"thread_id": "charm_session"}}
        if callbacks:
            config["callbacks"] = callbacks

        native_input = inputs.copy()

        # State Restoration
        raw_state = native_input.pop("__charm_state__", None)
        if raw_state and hasattr(self.agent, "update_state"):
            try:
                logger.debug("[Charm] Hydrating LangGraph state from snapshot...")
                saved_state = json.loads(base64.b64decode(raw_state).decode("utf-8"))
                self.agent.update_state(config, saved_state)
            except Exception as e:
                logger.warning(f"[Charm] Failed to restore state: {e}")

        history_data = native_input.pop("__charm_history__", None)

        if history_data and "messages" in native_input:
            lc_messages = self._convert_history_to_messages(history_data)
            if isinstance(native_input["messages"], list):
                native_input["messages"] = lc_messages + native_input["messages"]
            else:
                native_input["messages"] = lc_messages

        if "input" in native_input and "messages" not in native_input and len(native_input) == 1:
            logger.debug("[Charm] Converting simple 'input' to 'messages' for LangGraph.")
            native_input["messages"] = [HumanMessage(content=str(native_input["input"]))]
            del native_input["input"]

        result = None

        try:
            result = self.agent.invoke(native_input, config=config)
        except Exception as e:
            error_str = str(e).lower()
            if "no synchronous function" in error_str or "async" in error_str:
                logger.info("[Charm] Detected Async Graph. Switching to ainvoke...")
                try:
                    result = self._execute_async_safely(
                        self.agent.ainvoke(native_input, config=config)
                    )
                except Exception as async_e:
                    return {
                        "status": "error",
                        "message": f"Async Graph Execution Failed: {str(async_e)}",
                    }
            else:
                return {"status": "error", "message": f"Graph Execution Failed: {str(e)}"}

        # State Snapshot
        charm_state_payload = ""
        if hasattr(self.agent, "get_state"):
            try:
                snapshot = self.agent.get_state(config)
                if snapshot and hasattr(snapshot, "values"):
                    state_json = json.dumps(snapshot.values, default=str)
                    charm_state_payload = base64.b64encode(state_json.encode("utf-8")).decode(
                        "utf-8"
                    )
            except Exception as e:
                logger.warning(f"[Charm] Failed to snapshot state: {e}")

        try:
            output_str = ""

            if isinstance(result, dict):
                if "messages" in result:
                    messages = result["messages"]
                    if isinstance(messages, list) and len(messages) > 0:
                        last_msg = messages[-1]

                        content = getattr(last_msg, "content", "")
                        additional_kwargs = getattr(last_msg, "additional_kwargs", {})

                        if content and str(content).strip():
                            output_str = str(content)
                        elif hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            tools_desc = []
                            for tool in last_msg.tool_calls:
                                t_name = tool.get("name", "tool")
                                t_args = json.dumps(tool.get("args", {}))
                                tools_desc.append(f"🛠️ Call: {t_name}({t_args})")
                            output_str = "\n".join(tools_desc)
                        elif "function_call" in additional_kwargs:
                            fc = additional_kwargs["function_call"]
                            t_name = fc.get("name", "unknown_tool")
                            t_args = fc.get("arguments", "{}")
                            output_str = f"🛠️ Call (Legacy): {t_name}({t_args})"
                        elif hasattr(last_msg, "response_metadata"):
                            meta = last_msg.response_metadata
                            if "prompt_feedback" in meta:
                                output_str = f"Safety Block: {meta['prompt_feedback']}"
                            elif "finish_reason" in meta:
                                output_str = f"Stop Reason: {meta['finish_reason']}"
                            else:
                                output_str = f"(Empty Content. Raw Message: {str(last_msg)})"
                        else:
                            output_str = f"(Unknown Message Format: {str(last_msg)})"

                elif "generation" in result:
                    output_str = str(result["generation"])
                elif "result" in result:
                    output_str = str(result["result"])
                else:
                    # Try to find meaningful string values in the dict
                    output_str = json.dumps(result, ensure_ascii=False, default=str)

            else:
                output_str = str(result)

            if not output_str or not output_str.strip():
                output_str = f"(Agent returned empty content. Result Type: {type(result)})"

            return {
                "status": "success",
                "output": output_str,
                "charm_state": charm_state_payload,  # Return state for wrapper to broadcast
            }

        except Exception as e:
            return {"status": "error", "message": f"Output Processing Error: {str(e)}"}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
