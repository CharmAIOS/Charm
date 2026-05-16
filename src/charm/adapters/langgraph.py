import os
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from ..core.checkpoint import CharmSupabaseCheckpointer
from ..core.logger import logger
from .base import BaseAdapter

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    from langchain.schema import HumanMessage  # type: ignore


class CharmLangGraphAdapter(BaseAdapter):
    """
    Adapter for LangGraph with Supabase Persistence (HITL Support).
    """

    def _ensure_instantiated(self):
        self._smart_instantiate()

        # Setup Checkpointer via Storage Plugin
        from ..core.storage import StorageManager
        
        provider_name = "local"
        provider_config = {}
        
        # Backward compatibility for legacy env var
        if os.getenv("NEXT_PUBLIC_SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
            provider_name = "supabase"
            
        if hasattr(self, "config") and self.config and hasattr(self.config, "memory"):
            provider_name = self.config.memory.provider
            provider_config = self.config.memory.config
            
        provider = StorageManager.get_provider(provider_name, provider_config)
        self.checkpointer = provider.get_langgraph_checkpointer()
        
        if self.checkpointer:
            logger.info(f"💾 [Charm] Checkpointer Activated via {provider_name}.")
        else:
            logger.warning(f"⚠️ [Charm] Memory provider '{provider_name}' does not support LangGraph Checkpointing. HITL will use volatile RAM.")

        # Unwrap Wrapper Classes
        if not hasattr(self.agent, "invoke"):
            if hasattr(self.agent, "app") and hasattr(self.agent.app, "invoke"):
                self.agent = self.agent.app
            elif hasattr(self.agent, "graph") and hasattr(self.agent.graph, "invoke"):
                self.agent = self.agent.graph

        # Dynamic Compilation (Inject Checkpointer)
        if hasattr(self.agent, "compile"):
            logger.info("⚙️ [Charm] Compiling StateGraph with Persistence...")
            self.agent = self.agent.compile(checkpointer=self.checkpointer)

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        self._ensure_instantiated()

        # Thread ID Management
        thread_id = inputs.pop("thread_id", None) or inputs.pop(
            "__charm_thread_id__", "default_thread"
        )

        config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        if callbacks:
            config["callbacks"] = callbacks

        native_input = inputs.copy()

        # Normalize Inputs
        if "messages" not in native_input and "input" in native_input:
            native_input["messages"] = [HumanMessage(content=str(native_input.pop("input")))]

        if "messages" in native_input:
            current = native_input["messages"]
            if not isinstance(current, list):
                native_input["messages"] = [current]

        # Execution
        result = None
        try:
            result = self.agent.invoke(native_input, config=config)

            snapshot = self.agent.get_state(config)

            if snapshot.next:
                logger.info(f"⏸️ [Charm] HITL Suspended. Waiting for: {snapshot.next}")

                output_content = "Waiting for input..."
                if isinstance(result, dict) and "messages" in result and result["messages"]:
                    output_content = str(result["messages"][-1].content)

                return {
                    "status": "suspended",
                    "output": output_content,
                    "thread_id": thread_id,
                    "next_step": snapshot.next,
                    "charm_state": "",
                }

        except Exception as e:
            return {"status": "error", "message": f"Graph Execution Failed: {str(e)}"}

        # Success Handling
        output = str(result)
        if isinstance(result, dict):
            if "_charm_render_type" in result:
                output = result
            elif "messages" in result and result["messages"]:
                output = str(result["messages"][-1].content)
            elif "generation" in result:
                output = str(result["generation"])
            elif "output" in result:
                val = result["output"]
                if isinstance(val, dict) and "_charm_render_type" in val:
                    output = val
                else:
                    output = str(val)

        return {
            "status": "success",
            "output": output,
            "thread_id": thread_id,
            "charm_state": "",
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
