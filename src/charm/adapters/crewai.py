from typing import Any, Dict, List
import inspect
import asyncio
from .base import BaseAdapter
from ..core.logger import logger

class CharmCrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Framework."""

    def _ensure_instantiated(self):
        # 處理 Entry Point 是一個函式的情況 (Factory Pattern)
        if callable(self.agent) and not hasattr(self.agent, "kickoff"):
            try:
                print(f"[Charm] Entry point is a callable ({type(self.agent).__name__}), instantiating Crew object...")
                
                sig = inspect.signature(self.agent)
                params = sig.parameters
                
                # 自動判斷是否需要傳入參數
                if len(params) > 0:
                    self.agent = self.agent(self._pending_inputs)
                else:
                    self.agent = self.agent()

            except Exception as e:
                print(f"[Charm] Warning: Failed to instantiate factory function: {e}")

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._pending_inputs = inputs
        self._ensure_instantiated()

        # 檢查是否為有效的 Crew 物件
        if not hasattr(self.agent, "kickoff"):
             return {
                 "status": "error", 
                 "error_type": "CharmExecutionError",
                 "message": f"Entry point did not resolve to a CrewAI object. Got {type(self.agent).__name__} instead."
             }

        # 正規化 Input：CrewAI 習慣用 'topic'
        native_input = inputs
        if "input" in inputs and "topic" not in inputs:
            native_input = {"topic": inputs["input"], **inputs}

        result = None
        try:
            # 1. 優先嘗試同步執行 (標準 CrewAI)
            result = self.agent.kickoff(inputs=native_input)
        
        except Exception as e:
            # 2. 如果失敗，檢查是否是因為使用了 Async Tools
            # CrewAI 的 Async 方法通常叫 kickoff_async (舊) 或 akickoff (新)
            error_msg = str(e).lower()
            if "await" in error_msg or "async" in error_msg or "coroutine" in error_msg:
                logger.info("[Charm] Detected Async Crew requirements. Switching to async execution...")
                
                if hasattr(self.agent, "akickoff"): # 新版 CrewAI
                    result = self._execute_async_safely(self.agent.akickoff(inputs=native_input))
                elif hasattr(self.agent, "kickoff_async"): # 舊版 CrewAI
                    result = self._execute_async_safely(self.agent.kickoff_async(inputs=native_input))
                else:
                    return {"status": "error", "message": f"Async required but no async method found: {e}"}
            else:
                # 真的報錯了 (非 Async 問題)
                return {"status": "error", "message": str(e)}

        # 3. 處理輸出結果
        try:
            output_str = ""
            if hasattr(result, "raw"):
                output_str = result.raw
            else:
                output_str = str(result)

            return {"status": "success", "output": output_str}
        except Exception as e:
             return {"status": "error", "message": f"Output parsing error: {e}"}

    def get_state(self) -> Dict[str, Any]:
        self._ensure_instantiated()
        if hasattr(self.agent, "agents"):
            return {
                "agents": [a.role for a in self.agent.agents],
                "tasks_count": len(self.agent.tasks)
            }
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        self._ensure_instantiated()
        if hasattr(self.agent, "agents"):
            for agent in self.agent.agents:
                if not hasattr(agent, "tools"):
                    agent.tools = []
                agent.tools.extend(tools)