import inspect
from typing import Any, Dict, Generator, Union
from .base import BaseAdapter
from ..core.logger import logger

class CharmCustomAdapter(BaseAdapter):

    def __init__(self, agent_instance: Any):
        super().__init__(agent_instance)
        self.execution_method = self._discover_execution_method(agent_instance)
        logger.debug(f"Custom Adapter bound to: {self.execution_method.__name__}")

    def _discover_execution_method(self, instance: Any):
        # 優先順序：invoke > run > __call__
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
            # [核心優化] 使用 BaseAdapter 的智能調用，自動處理 Async
            result = self._smart_invoke(self.execution_method, inputs)
            
            if isinstance(result, dict):
                return result
            elif isinstance(result, str):
                return {"output": result}
            else:
                return {"output": str(result), "raw_type": type(result).__name__}
                
        except Exception as e:
            logger.error(f"Custom Agent crashed: {e}")
            raise e # 拋出給外層捕獲，或者回傳錯誤結構

    def stream(self, inputs: Dict[str, Any]) -> Generator[Any, None, None]:
        """
        支援 Python Generator (yield) 以及 Async Generator
        """
        # 如果使用者實作了 stream 方法
        if hasattr(self.agent, "stream") and callable(self.agent.stream):
            yield from self.agent.stream(inputs)
            return

        # 如果 execution_method 本身是 generator
        if inspect.isgeneratorfunction(self.execution_method):
            yield from self.execution_method(inputs)
            return
            
        # 如果以上都不是，退回一般 invoke
        result = self.invoke(inputs)
        yield result