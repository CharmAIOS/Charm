import inspect
from typing import Any, Dict, Generator, List, Optional

from ..core.logger import logger
from .base import BaseAdapter


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

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info("Executing Custom Agent...")
        try:
            # Smart Argument Binding & Contract Validation
            sig = inspect.signature(self.execution_method)
            kwargs: Dict[str, Any] = {}

            missing_args = []

            for name, param in sig.parameters.items():
                if name == "inputs":
                    kwargs["inputs"] = inputs
                elif name == "callbacks":
                    kwargs["callbacks"] = callbacks

                elif name in inputs:
                    kwargs[name] = inputs[name]

                elif param.default != inspect.Parameter.empty:
                    continue

                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    continue

                else:
                    missing_args.append(name)

            if missing_args:
                error_msg = (
                    f"Agent function '{self.execution_method.__name__}' requires arguments {missing_args} "
                    f"which are not provided by Charm Runtime.\n"
                    f"Available system arguments: ['inputs', 'callbacks'] or keys inside your input payload.\n"
                    f"Suggested Fix: Update signature to 'def {self.execution_method.__name__}(inputs, callbacks=None):'"
                )
                logger.error(error_msg)
                return {"status": "error", "error_type": "ContractViolation", "message": error_msg}

            result = self._smart_invoke(self.execution_method, **kwargs)

            if isinstance(result, dict):
                return result
            elif isinstance(result, str):
                return {"output": result}
            else:
                return {"output": str(result), "raw_type": type(result).__name__}

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
            if "callbacks" in sig.parameters:
                kwargs["callbacks"] = callbacks
            if "inputs" in sig.parameters:
                kwargs["inputs"] = inputs
            else:
                # Fallback
                if len(sig.parameters) == 1:
                    kwargs = {"inputs": inputs}
                else:
                    kwargs = inputs

            yield from self.agent.stream(**kwargs)
            return

        if inspect.isgeneratorfunction(self.execution_method):
            yield from self.execution_method(inputs)
            return

        result = self.invoke(inputs, callbacks=callbacks)
        yield result

    def set_tools(self, tools: List[Any]) -> None:
        pass
