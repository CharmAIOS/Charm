from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from .io import CharmEmitter

class CharmCallbackHandler(BaseCallbackHandler):
    """
    Charm 通用回調處理器
    負責監聽 LangChain / CrewAI 的內部事件，並轉換為 Charm SSE 協議。
    解決了日誌雜訊和框線問題。
    """
    
    def __init__(self):
        self.current_tool = None
        self.ignore_llm = False # 是否忽略 LLM 思考過程 (避免太吵)

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        """當 Agent 開始使用工具時 -> Thinking"""
        tool_name = serialized.get("name", "Unknown Tool")
        self.current_tool = tool_name
        # 格式化輸出，讓前端 Thinking 區塊看起來整齊
        msg = f"🛠️ Using Tool: {tool_name}\nInput: {input_str}\n"
        CharmEmitter.emit_thinking(msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """當工具執行結束時 -> Thinking"""
        # 這裡的 output 是純文字，沒有任何 rich 框線
        msg = f"✅ Tool Output: {str(output)[:500]}...\n" # 截斷過長輸出
        CharmEmitter.emit_thinking(msg)
        self.current_tool = None

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        """當工具出錯時 -> Thinking (Error)"""
        msg = f"❌ Tool Error: {str(error)}\n"
        CharmEmitter.emit_thinking(msg)

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        """當 LLM 開始思考時"""
        # 可以在這裡決定是否要顯示 Prompt，目前先保持安靜
        pass

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        """
        [關鍵] 當 LLM 生成文字時 -> Delta (Streaming)
        這讓我們能做到像 ChatGPT 那樣的打字機效果。
        """
        # 注意：這個 token 是原始文字，沒有格式
        CharmEmitter.emit_delta(token)

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """Agent 決定採取行動"""
        tool = getattr(action, "tool", "Unknown")
        inp = getattr(action, "tool_input", "")
        # 有時候 on_tool_start 不會觸發 (取決於 agent 類型)，這裡補強
        if not self.current_tool:
             CharmEmitter.emit_thinking(f"🤔 Thought: I need to use {tool} with {inp}\n")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        """當 Chain 結束時"""
        # 我們通常依賴 wrapper.py 的最終返回，或者 on_llm_new_token 的累積
        # 但如果是 CrewAI，它可能不會串流，所以這裡不強制 emit final
        pass