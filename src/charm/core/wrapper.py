import sys
from typing import Any, Dict, List, Optional, Generator
from ..adapters.base import BaseAdapter
from .errors import CharmExecutionError
from .logger import logger
from .io import CharmEmitter, StdoutInterceptor  # [New]

class CharmWrapper:
    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        CharmEmitter.emit_status("Initializing Agent Runtime...")
        
        # [New] 替換 stdout，開始攔截所有 print 為 thinking
        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()
        
        try:
            result = self.adapter.invoke(inputs)
            
            # 執行結束，將結果作為 Final Event 發送
            if result.get("status") == "success":
                CharmEmitter.emit_final(result.get("output", ""))
                return result
            else:
                error_msg = result.get("message", "Unknown error")
                CharmEmitter.emit_error(error_msg)
                return result
                
        except Exception as e:
            CharmEmitter.emit_error(str(e))
            return {
                "status": "error",
                "error_type": "CharmExecutionError",
                "message": str(e)
            }
        finally:
            # [New] 還原 stdout，確保後續系統操作正常
            sys.stdout = original_stdout

    def stream(self, inputs: Dict[str, Any]) -> Generator[Any, None, None]:
        # Stream 模式同樣需要攔截
        CharmEmitter.emit_status("Streaming Agent Runtime...")
        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()

        try:
            if hasattr(self.adapter, "stream"):
                for chunk in self.adapter.stream(inputs):
                    # 這裡假設 adapter stream 回傳的是中間結果
                    # 實際應用中可能需要根據 chunk 類型決定是 thinking 還是 final
                    # 簡單起見，這裡暫不處理 adapter 內部的流，而是依賴 StdoutInterceptor 抓 log
                    yield chunk
            else:
                yield self.invoke(inputs)
                
        except Exception as e:
            CharmEmitter.emit_error(str(e))
            yield {
                "status": "error",
                "error_type": "CharmExecutionError",
                "message": str(e)
            }
        finally:
            sys.stdout = original_stdout

    def get_state(self) -> Dict[str, Any]:
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        self.adapter.set_tools(tools)