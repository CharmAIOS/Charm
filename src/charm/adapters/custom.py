import inspect
from typing import Any, Dict, Generator, Union
from .base import BaseAdapter
from ..core.logger import logger

class CharmCustomAdapter(BaseAdapter):

    def __init__(self, agent_instance: Any):
        super().__init__(agent_instance)
        self._smart_instantiate()
        self.execution_method = self._discover_execution_method(self.agent)
        logger.debug(f"Custom Adapter bound to: {self.execution_method.__name__}")

    def _discover_execution_method(self, instance: Any):
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
            result = self._smart_invoke(self.execution_method, inputs)
            
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
        if hasattr(self.agent, "stream") and callable(self.agent.stream):
            yield from self.agent.stream(inputs)
            return

        if inspect.isgeneratorfunction(self.execution_method):
            yield from self.execution_method(inputs)
            return
            
        result = self.invoke(inputs)
        yield result