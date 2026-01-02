from typing import Any, Dict, Optional

from langchain_core.callbacks import BaseCallbackHandler

from .io import CharmEmitter


class CharmCallbackHandler(BaseCallbackHandler):
    """
    Custom LangChain Callback to capture execution events and stream them via CharmEmitter.
    """

    ignore_llm: bool = False
    ignore_chain: bool = False
    ignore_agent: bool = False
    ignore_retriever: bool = False
    always_verbose: bool = True

    def __init__(self, shared_state: Optional[Dict[str, Any]] = None):
        self.current_tool = None
        # Shared state allows the wrapper to know if tokens were streamed.
        self.shared_state = shared_state if shared_state is not None else {}

        print("[Charm] Loaded Local SDK Fix (Shared State + Attrs)")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        """Triggered when a tool starts executing."""
        tool_name = serialized.get("name", "Unknown Tool")
        self.current_tool = tool_name
        msg = f"Using Tool: {tool_name}\nInput: {input_str}\n"
        CharmEmitter.emit_thinking(msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Triggered when a tool finishes."""
        out_str = str(output)
        msg = f"Tool Output: {out_str[:500]}...\n"  # Truncate long outputs
        CharmEmitter.emit_thinking(msg)
        self.current_tool = None

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        """Triggered on tool failure."""
        msg = f"Tool Error: {str(error)}\n"
        CharmEmitter.emit_thinking(msg)

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        """
        Triggered when LLM emits a new token (Streaming).
        """
        if token:
            self.shared_state["has_streamed"] = True
            CharmEmitter.emit_delta(token)

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """Capture the agent's thought process."""
        tool = getattr(action, "tool", "Unknown")
        inp = getattr(action, "tool_input", "")
        if isinstance(inp, dict):
            inp = str(inp)

        if not self.current_tool:
            CharmEmitter.emit_thinking(f"Thought: I need to use {tool} with {inp}\n")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        pass
