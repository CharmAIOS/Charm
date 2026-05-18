from typing import Any, Dict, Optional

from langchain_core.callbacks import BaseCallbackHandler

from .telemetry import TelemetryManager


class CharmCallbackHandler(BaseCallbackHandler):
    """
    Custom LangChain Callback to capture execution events and stream them via TelemetryManager.
    """

    ignore_llm: bool = False
    ignore_chain: bool = False
    ignore_agent: bool = False
    ignore_retriever: bool = False
    always_verbose: bool = True

    def __init__(self, shared_state: Optional[Dict[str, Any]] = None, telemetry_manager: Optional[TelemetryManager] = None):
        self.current_tool = None
        # Shared state allows the wrapper to know if tokens were streamed.
        self.shared_state = shared_state if shared_state is not None else {}
        self.telemetry = telemetry_manager or TelemetryManager()

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        """Triggered when a tool starts executing."""
        tool_name = serialized.get("name", "Unknown Tool")
        self.current_tool = tool_name
        self.telemetry.dispatch("on_tool_start", tool_name=tool_name, input_str=input_str)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Triggered when a tool finishes."""
        out_str = str(output)
        self.telemetry.dispatch("on_tool_end", tool_name=self.current_tool or "Unknown", output=out_str)
        self.current_tool = None

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        """Triggered on tool failure."""
        self.telemetry.dispatch("on_tool_error", tool_name=self.current_tool or "Unknown", error=error)

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        """
        Triggered when LLM emits a new token (Streaming).
        """
        if token:
            self.shared_state["has_streamed"] = True
            self.telemetry.dispatch("on_llm_new_token", token=token)

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """Capture the agent's thought process."""
        tool = getattr(action, "tool", "Unknown")
        inp = getattr(action, "tool_input", "")
        if not self.current_tool:
            self.telemetry.dispatch("on_agent_action", tool=tool, tool_input=inp)

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        pass
