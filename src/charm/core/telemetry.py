from abc import ABC, abstractmethod
from typing import Any, Dict

from .io import CharmEmitter


class BaseTelemetryExporter(ABC):
    """Base interface for all Charm Telemetry Exporters."""

    @abstractmethod
    def on_run_start(self, run_id: str, inputs: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def on_run_end(self, run_id: str, outputs: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def on_error(self, run_id: str, error: Exception) -> None:
        pass

    @abstractmethod
    def on_tool_start(self, tool_name: str, input_str: str) -> None:
        pass

    @abstractmethod
    def on_tool_end(self, tool_name: str, output: str) -> None:
        pass

    @abstractmethod
    def on_tool_error(self, tool_name: str, error: BaseException) -> None:
        pass

    @abstractmethod
    def on_llm_new_token(self, token: str) -> None:
        pass

    @abstractmethod
    def on_agent_action(self, tool: str, tool_input: str) -> None:
        pass


class CharmEmitterExporter(BaseTelemetryExporter):
    """The default exporter that streams events to the Charm Cloud Runner via stdout."""

    def on_run_start(self, run_id: str, inputs: Dict[str, Any]) -> None:
        pass

    def on_run_end(self, run_id: str, outputs: Dict[str, Any]) -> None:
        pass

    def on_error(self, run_id: str, error: Exception) -> None:
        pass

    def on_tool_start(self, tool_name: str, input_str: str) -> None:
        CharmEmitter.emit_thinking(f"Using Tool: {tool_name}\nInput: {input_str}\n")

    def on_tool_end(self, tool_name: str, output: str) -> None:
        CharmEmitter.emit_thinking(f"Tool Output: {str(output)[:500]}...\n")

    def on_tool_error(self, tool_name: str, error: BaseException) -> None:
        CharmEmitter.emit_thinking(f"Tool Error: {str(error)}\n")

    def on_llm_new_token(self, token: str) -> None:
        if token:
            CharmEmitter.emit_delta(token)

    def on_agent_action(self, tool: str, tool_input: str) -> None:
        if isinstance(tool_input, dict):
            tool_input = str(tool_input)
        CharmEmitter.emit_thinking(f"Thought: I need to use {tool} with {tool_input}\n")


class TelemetryManager:
    """Manages the lifecycle and event dispatching for telemetry plugins."""

    def __init__(self, enabled_exporters: list[str] | None = None):
        self.enabled_exporters = enabled_exporters or []
        self.exporters: list[BaseTelemetryExporter] = [CharmEmitterExporter()]
        self._load_plugins()

    def _load_plugins(self):
        from importlib.metadata import entry_points
        try:
            eps = entry_points(group="charm.telemetry")
            for ep in eps:
                if ep.name in self.enabled_exporters:
                    try:
                        exporter_class = ep.load()
                        self.exporters.append(exporter_class())
                    except Exception as e:
                        from .logger import logger
                        logger.warning(f"Failed to load telemetry exporter {ep.name}: {e}")
        except Exception:
            pass

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any):
        """Dispatch an event to all registered telemetry exporters."""
        for exporter in self.exporters:
            try:
                getattr(exporter, event_name)(*args, **kwargs)
            except Exception as e:
                from .logger import logger
                logger.debug(f"Telemetry exporter {exporter.__class__.__name__} failed on {event_name}: {e}")
