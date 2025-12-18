import inspect
from typing import Any, Dict, Generator, Union
from .base import BaseAdapter
from ..core.logger import logger

class CharmCustomAdapter(BaseAdapter):
    """
    Universal Adapter for Pure Python Agents.
    Strategy: Duck Typing (如果它走起來像鴨子，它就是鴨子)
    """

    def __init__(self, agent_instance: Any):
        super().__init__(agent_instance)
        # 在初始化時就決定要用哪種方式執行，避免執行時才判斷，提升效能
        self.execution_method = self._discover_execution_method(agent_instance)
        logger.debug(f"Custom Adapter bound to: {self.execution_method.__name__}")

    def _discover_execution_method(self, instance: Any):
        """
        自動偵測入口點。優先順序：
        1. invoke(dict) -> 標準 Charm/LangChain 模式
        2. run(dict)    -> 常見腳本模式
        3. __call__     -> 函數或 Callable 物件
        """
        if hasattr(instance, "invoke") and callable(instance.invoke):
            return instance.invoke
        elif hasattr(instance, "run") and callable(instance.run):
            return instance.run
        elif callable(instance):
            return instance
        else:
            raise TypeError(
                f"Agent entry point '{type(instance).__name__}' is not valid. "
                "It must be a function, or a class with 'invoke()' or 'run()' methods."
            )

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Executing Custom Agent...")
        try:
            # 執行用戶代碼
            result = self.execution_method(inputs)
            
            # 🛡️ 輸出標準化 (Output Normalization)
            # 因為 Custom Agent 可能回傳字串、數字或字典，我們必須確保 Runner 拿到的是字典
            if isinstance(result, dict):
                return result
            elif isinstance(result, str):
                return {"output": result}
            else:
                return {"output": str(result), "raw_type": type(result).__name__}
                
        except Exception as e:
            logger.error(f"Custom Agent crashed: {e}")
            raise e

    def stream(self, inputs: Dict[str, Any]) -> Generator[Any, None, None]:
        """
        支援 Python Generator (yield)
        """
        # 1. 優先檢查是否實作了標準 stream 方法
        if hasattr(self.agent, "stream") and callable(self.agent.stream):
            yield from self.agent.stream(inputs)
            return

        # 2. 檢查執行方法本身是不是 Generator
        if inspect.isgeneratorfunction(self.execution_method):
            yield from self.execution_method(inputs)
            return
            
        # 3. 如果都不是，退回單次執行 (Wrapper 會處理這部分，但這裡顯式處理更安全)
        result = self.invoke(inputs)
        yield result