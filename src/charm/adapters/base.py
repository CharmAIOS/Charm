from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Generator
import asyncio
import inspect

class BaseAdapter(ABC):
    
    def __init__(self, agent_instance: Any):
        self.agent = agent_instance
        self._pending_inputs: Dict[str, Any] = {}

    @abstractmethod
    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def stream(self, inputs: Dict[str, Any]) -> Generator[Any, None, None]:
        result = self.invoke(inputs)
        yield result

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass

    def _execute_async_safely(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)

    def _smart_invoke(self, func, *args, **kwargs):
        if inspect.iscoroutinefunction(func):
            return self._execute_async_safely(func(*args, **kwargs))
        
        result = func(*args, **kwargs)
        
        if inspect.iscoroutine(result):
            return self._execute_async_safely(result)
            
        return result