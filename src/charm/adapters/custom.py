import inspect
from typing import Any, Dict, Generator, List, Optional

from ..core.logger import logger
from .base import BaseAdapter


class CharmCustomAdapter(BaseAdapter):
    def __init__(self, agent_instance: Any):
        super().__init__(agent_instance)

        if inspect.isclass(self.agent):
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

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info("Executing Custom Agent...")
        try:
            sig = inspect.signature(self.execution_method)
            kwargs: Dict[str, Any] = {}

            if len(sig.parameters) > 0:
                for name, param in sig.parameters.items():
                    if name == "inputs":
                        kwargs["inputs"] = inputs
                    elif name == "callbacks":
                        kwargs["callbacks"] = callbacks

                    # 2. Destructuring Injection
                    elif name in inputs:
                        kwargs[name] = inputs[name]

                    # 3. Catch-all (**kwargs)
                    elif param.kind == inspect.Parameter.VAR_KEYWORD:
                        kwargs.update(inputs)

                    # 4. Default values
                    elif param.default != inspect.Parameter.empty:
                        continue

                    # 5. Missing required args: We do nothing and let Python raise TypeError
                    else:
                        pass

            result = self._smart_invoke(self.execution_method, **kwargs)

            if isinstance(result, dict) and "status" in result:
                return result

            return {
                "status": "success",
                "output": result,
                "raw_type": type(result).__name__,
            }

        except TypeError as e:
            error_msg = (
                f"Function signature mismatch for '{self.execution_method.__name__}': {str(e)}"
            )
            logger.error(error_msg)
            return {"status": "error", "error_type": "SignatureError", "message": error_msg}
        except Exception as e:
            logger.error(f"Custom Agent crashed: {e}")
            return {
                "status": "error",
                "error_type": "RuntimeError",
                "message": f"Agent Execution Failed: {str(e)}",
            }

    def stream(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Generator[Any, None, None]:
        if hasattr(self.agent, "stream") and callable(self.agent.stream):
            sig = inspect.signature(self.agent.stream)
            kwargs: Dict[str, Any] = {}

            if len(sig.parameters) > 0:
                if "callbacks" in sig.parameters:
                    kwargs["callbacks"] = callbacks
                if "inputs" in sig.parameters:
                    kwargs["inputs"] = inputs
                else:
                    # Fallback logic
                    if len(sig.parameters) == 1:
                        kwargs = {"inputs": inputs}
                    else:
                        # Destructuring attempt
                        for k, v in inputs.items():
                            if k in sig.parameters:
                                kwargs[k] = v

            yield from self.agent.stream(**kwargs)
            return

        if inspect.isgeneratorfunction(self.execution_method):
            yield from self.execution_method(inputs)
            return

        result = self.invoke(inputs, callbacks=callbacks)
        yield result

    def set_tools(self, tools: List[Any]) -> None:
        pass
