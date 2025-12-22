from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from .io import CharmEmitter

class CharmCallbackHandler(BaseCallbackHandler):
    
    def __init__(self):
        self.current_tool = None

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        tool_name = serialized.get("name", "Unknown Tool")
        self.current_tool = tool_name
        msg = f"Using Tool: {tool_name}\nInput: {input_str}\n"
        CharmEmitter.emit_thinking(msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        msg = f"Tool Output: {str(output)[:500]}...\n" 
        CharmEmitter.emit_thinking(msg)
        self.current_tool = None

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        msg = f"Tool Error: {str(error)}\n"
        CharmEmitter.emit_thinking(msg)

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        pass

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        CharmEmitter.emit_delta(token)

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        tool = getattr(action, "tool", "Unknown")
        inp = getattr(action, "tool_input", "")
        if not self.current_tool:
             CharmEmitter.emit_thinking(f"Thought: I need to use {tool} with {inp}\n")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        pass