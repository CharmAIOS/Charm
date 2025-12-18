from typing import Any, Dict, List, Optional, Generator
from ..adapters.base import BaseAdapter
from .errors import CharmExecutionError
from .logger import logger

class CharmWrapper:
    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Invoking agent via CharmWrapper...")
        try:
            return self.adapter.invoke(inputs)
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")

            return {
                "status": "error",
                "error_type": "CharmExecutionError",
                "message": str(e)
            }

    def stream(self, inputs: Dict[str, Any]) -> Generator[Any, None, None]:
        """
        Stream the agent execution. 
        If the underlying adapter supports streaming, yield chunks.
        Otherwise, fall back to invoke() and yield the result as a single chunk.
        """
        logger.info("Streaming agent via CharmWrapper...")
        try:
            # 檢查 Adapter 是否有實作 stream 方法
            if hasattr(self.adapter, "stream"):
                yield from self.adapter.stream(inputs)
            else:
                # Fallback: 對於不支援串流的 Adapter（例如 CrewAI 某些舊版），
                # 我們執行 invoke 並把結果當作「單次串流」回傳，保持介面一致性。
                logger.debug("Adapter does not support streaming, falling back to invoke.")
                yield self.invoke(inputs)
                
        except Exception as e:
            logger.error(f"Agent streaming failed: {e}")
            # 發生錯誤時，回傳一個包含錯誤資訊的物件，讓前端能顯示紅字
            yield {
                "status": "error",
                "error_type": "CharmExecutionError",
                "message": str(e)
            }

    def get_state(self) -> Dict[str, Any]:
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        self.adapter.set_tools(tools)