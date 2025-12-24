from typing import Any, Dict, List
import inspect
import asyncio 
import json
from .base import BaseAdapter
from ..core.logger import logger

try:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
except ImportError:
    from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage # type: ignore

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

    def _convert_history_to_messages(self, history: List[Dict[str, str]]) -> List[Any]:
        lc_messages = []
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

    def invoke(self, inputs: Dict[str, Any], callbacks: List[Any] = None) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()

        config = {"configurable": {"thread_id": "charm_default_thread"}}
        if callbacks:
            config["callbacks"] = callbacks

        native_input = inputs.copy()
        
        history_data = native_input.pop("__charm_history__", None)
        lc_messages = []
        
        if history_data:
            lc_messages.extend(self._convert_history_to_messages(history_data))

        user_input_content = native_input.get("input") or native_input.get("task") or native_input.get("topic")
        has_user_input = user_input_content and str(user_input_content).strip()

        if has_user_input:
             lc_messages.append(HumanMessage(content=str(user_input_content)))
        
        elif not history_data and not has_user_input:
             logger.info("[Charm] Auto-injecting kickoff message for fresh session.")
             lc_messages.append(HumanMessage(content="Hello, please start."))

        if "messages" in native_input and isinstance(native_input["messages"], list):
            native_input["messages"] = lc_messages + native_input["messages"]
        else:
            native_input["messages"] = lc_messages

        # [Important] Do NOT delete input key
        # if "input" in native_input: del native_input["input"]

        result = None

        try:
            result = self.agent.invoke(native_input, config=config)
        except Exception as e:
            error_str = str(e).lower()
            if "no synchronous function" in error_str or "async" in error_str:
                logger.info("[Charm] Detected Async Graph. Switching to ainvoke...")
                try:
                    result = self._execute_async_safely(self.agent.ainvoke(native_input, config=config))
                except Exception as async_e:
                    return {"status": "error", "message": f"Async Graph Execution Failed: {str(async_e)}"}
            else:
                return {"status": "error", "message": f"Graph Execution Failed: {str(e)}"}

        try:
            output_str = ""

            if isinstance(result, dict):
                if "messages" in result:
                    messages = result["messages"]
                    if isinstance(messages, list) and len(messages) > 0:
                        last_msg = messages[-1]
                        
                        content = getattr(last_msg, "content", "")
                        additional_kwargs = getattr(last_msg, "additional_kwargs", {})
                        
                        # 1. Standard Content
                        if content and str(content).strip():
                            output_str = str(content)
                        
                        # 2. Standard Tool Calls (New LangChain)
                        elif hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            tools_desc = []
                            for tool in last_msg.tool_calls:
                                t_name = tool.get("name", "tool")
                                t_args = json.dumps(tool.get("args", {}))
                                tools_desc.append(f"🛠️ Call: {t_name}({t_args})")
                            output_str = "\n".join(tools_desc)

                        # 3. Legacy/Gemini Function Calls (Hidden in additional_kwargs)
                        elif "function_call" in additional_kwargs:
                            fc = additional_kwargs["function_call"]
                            t_name = fc.get("name", "unknown_tool")
                            t_args = fc.get("arguments", "{}")
                            output_str = f"🛠️ Call (Legacy): {t_name}({t_args})"
                            
                        # 4. Gemini Metadata / Safety Filters
                        elif hasattr(last_msg, "response_metadata"):
                            meta = last_msg.response_metadata
                            if "prompt_feedback" in meta:
                                output_str = f"⚠️ Safety Block: {meta['prompt_feedback']}"
                            elif "finish_reason" in meta:
                                output_str = f"⚠️ Stop Reason: {meta['finish_reason']}"
                            else:
                                # Last Resort: Dump the raw message for debugging
                                output_str = f"(Empty Content. Raw Message: {str(last_msg)})"
                        
                        else:
                            output_str = f"(Unknown Message Format: {str(last_msg)})"
                        # --- [FIX END] ---
                
                elif "generation" in result:
                    output_str = str(result["generation"])
                elif "result" in result:
                    output_str = str(result["result"])
            
            else:
                output_str = str(result)
            
            if not output_str or not output_str.strip():
                output_str = f"(Agent returned empty content. Result Type: {type(result)})"

            return {"status": "success", "output": output_str}
            
        except Exception as e:
            return {"status": "error", "message": f"Output Processing Error: {str(e)}"}

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass