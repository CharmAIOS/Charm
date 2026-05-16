import sys
from typing import Any, Dict, List, Optional

from ..adapters.base import BaseAdapter
from .callbacks import CharmCallbackHandler
from .io import CharmEmitter, StdoutInterceptor
from .logger import logger
from .telemetry import TelemetryManager


class CharmWrapper:
    """
    The runtime container that orchestrates the execution lifecycle.
    """

    def __init__(self, adapter: BaseAdapter, config: Optional[Any] = None):
        self.adapter = adapter
        self.config = config

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution entry point. Handles I/O interception and error handling.
        """
        CharmEmitter.emit_status("Initializing Agent Runtime...")

        # Handle None or non-dict inputs gracefully
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            logger.warning(f"[Charm] Input is not a dict: {type(inputs)}. Wrapping in 'input'.")
            inputs = {"input": inputs}

        logger.debug(f"[Charm] Invoking Adapter with keys: {list(inputs.keys())}")

        # Hijack Stdout
        original_stdout = sys.stdout
        sys.stdout = StdoutInterceptor()

        # Track streaming state to avoid double-printing final output
        stream_state = {"has_streamed": False}
        enabled_telemetry = self.config.runtime.telemetry if self.config and self.config.runtime else []
        telemetry = TelemetryManager(enabled_exporters=enabled_telemetry)
        telemetry.dispatch("on_run_start", run_id="local", inputs=inputs)
        charm_callback = CharmCallbackHandler(shared_state=stream_state, telemetry_manager=telemetry)

        try:
            # Execute via Adapter
            result = self.adapter.invoke(inputs, callbacks=[charm_callback])
            telemetry.dispatch("on_run_end", run_id="local", outputs=result)

            # State Broadcasting
            if "charm_state" in result and result["charm_state"]:
                CharmEmitter._write("state_update", {"content": result["charm_state"]})

            if result.get("status") == "suspended":
                CharmEmitter._write(
                    "control",
                    {
                        "status": "suspended",
                        "thread_id": result.get("thread_id"),
                        "next_step": result.get("next_step"),
                    },
                )
                if "output" in result:
                    CharmEmitter.emit_final(result["output"])
                return result

            if result.get("status") == "success":
                if not stream_state.get("has_streamed", False):
                    CharmEmitter.emit_final(result.get("output", ""))
                return result
            else:
                # Handle logical errors from the agent
                error_msg = result.get("message", "Unknown error")
                telemetry.dispatch("on_error", run_id="local", error=Exception(error_msg))
                CharmEmitter.emit_error(error_msg)
                sys.exit(0)  # Exit gracefully for the runner
                return result

        except Exception as e:
            # Global Error Handler
            telemetry.dispatch("on_error", run_id="local", error=e)
            CharmEmitter.emit_error(str(e))
            sys.exit(0)
            return {"status": "error", "error_type": "CharmExecutionError", "message": str(e)}
        finally:
            # Restore Stdout
            sys.stdout = original_stdout

    def get_state(self) -> Dict[str, Any]:
        """Delegate state retrieval to adapter."""
        try:
            return self.adapter.get_state()
        except Exception as e:
            logger.warning(f"Failed to get state: {e}")
            return {}

    def set_tools(self, tools: List[Any]) -> None:
        """Delegate tool injection."""
        self.adapter.set_tools(tools)
