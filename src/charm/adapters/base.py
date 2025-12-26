import asyncio
import inspect
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional

try:
    from ..core.logger import logger
except ImportError:
    logger = logging.getLogger("charm.adapter")


class BaseAdapter(ABC):
    def __init__(self, agent_instance: Any):
        self.agent = agent_instance
        self._pending_inputs: Dict[str, Any] = {}

    @abstractmethod
    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        pass

    def stream(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Generator[Any, None, None]:
        result = self.invoke(inputs, callbacks=callbacks)
        yield result

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:  # noqa: B027
        pass

    def _execute_async_safely(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            # Handle case where an event loop is already running (e.g. inside Jupyter or another async app)
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)

    def _smart_invoke(self, func, *args, **kwargs):
        if inspect.iscoroutinefunction(func):
            return self._execute_async_safely(func(*args, **kwargs))

        result = func(*args, **kwargs)

        if inspect.iscoroutine(result):
            return self._execute_async_safely(result)

        return result

    def _smart_instantiate(self):
        if not callable(self.agent):
            return

        if (
            hasattr(self.agent, "invoke")
            or hasattr(self.agent, "kickoff")
            or hasattr(self.agent, "run")
        ):
            return

        try:
            logger.debug(f"[Charm] Auto-instantiating {type(self.agent).__name__}...")
            sig = inspect.signature(self.agent)

            if len(sig.parameters) == 0:
                self.agent = self.agent()
            else:
                try:
                    # Try injecting inputs
                    self.agent = self.agent(self._pending_inputs)
                except TypeError:
                    # Fallback
                    self.agent = self.agent()

        except Exception as e:
            logger.warning(f"[Charm] Auto-instantiation failed: {e}")
