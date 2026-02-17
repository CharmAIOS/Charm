import json
import os
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

from ..core.logger import logger
from ..core.io import CharmEmitter
from ..core.checkpoint import CharmSupabaseCheckpointer
from .base import BaseAdapter

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
except ImportError:
    from langchain.schema import AIMessage, HumanMessage, SystemMessage  # type: ignore


class CharmLangGraphAdapter(BaseAdapter):
    """
    Adapter for LangGraph with Supabase Persistence (HITL Support).
    """

    def _ensure_instantiated(self):
        self._smart_instantiate()

        # Setup Supabase Checkpointer
        self.checkpointer = None
        sb_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if sb_url and sb_key:
            try:
                supabase: Client = create_client(sb_url, sb_key)
                self.checkpointer = CharmSupabaseCheckpointer(client=supabase)
                logger.info("💾 [Charm] Supabase Checkpointer Activated.")
            except Exception as e:
                logger.error(f"❌ [Charm] Checkpointer init failed: {e}")
        else:
            logger.warning("⚠️ [Charm] No DB credentials. HITL will strictly use RAM (volatile).")

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
        self._ensure_instantiated()

        # Thread ID Management
        thread_id = inputs.pop("thread_id", None) or inputs.pop(
            "__charm_thread_id__", "default_thread"
        )

        config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        if callbacks:
            config["callbacks"] = callbacks

        native_input = inputs.copy()

        # Context Injection (Profile & History)
        history_data = native_input.pop("__charm_history__", None)
        lc_history = []
        if history_data:
            lc_history = self._convert_history_to_messages(history_data[-10:])

        # Normalize Inputs
        if "messages" not in native_input and "input" in native_input:
            native_input["messages"] = [HumanMessage(content=str(native_input.pop("input")))]

        if "messages" in native_input:
            current = native_input["messages"]
            if not isinstance(current, list):
                current = [current]

            final_msgs = []
            if profile := self._get_user_profile():
                final_msgs.append(SystemMessage(content=f"User Profile: {profile}"))
            final_msgs.extend(lc_history)
            final_msgs.extend(current)
            native_input["messages"] = final_msgs

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
        output_str = str(result)
        if isinstance(result, dict):
            if "messages" in result and result["messages"]:
                output_str = str(result["messages"][-1].content)
            elif "generation" in result:
                output_str = str(result["generation"])
            elif "output" in result:
                output_str = str(result["output"])

        return {
            "status": "success",
            "output": output_str,
            "thread_id": thread_id,
            "charm_state": "",
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
