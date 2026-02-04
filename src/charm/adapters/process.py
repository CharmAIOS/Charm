import json
import logging
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional

from ..core.logger import logger
from .base import BaseAdapter


class CharmProcessAdapter(BaseAdapter):
    """
    Adapter for running external processes (e.g., Node.js, Go).
    It writes the input to 'input.json' and executes the entry_point command.
    """

    def __init__(self, command: str):
        self.command = command
        super().__init__(None)

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info(f"Executing Process Agent via command: {self.command}")

        # 1. Prepare Input Payload
        input_path = os.path.join(os.getcwd(), "input.json")
        native_input = inputs.copy()

        # Inject User Profile
        user_profile = self._get_user_profile()
        if user_profile:
            native_input["user_profile"] = user_profile

        # Clean up History (Truncate to last 10 interactions)
        raw_history = native_input.pop("__charm_history__", [])
        if raw_history:
            native_input["chat_history"] = raw_history[-10:]
        else:
            native_input["chat_history"] = []

        try:
            with open(input_path, "w", encoding="utf-8") as f:
                json.dump(native_input, f, ensure_ascii=False)
        except Exception as e:
            return {"status": "error", "message": f"Failed to write input.json: {e}"}

        # 2. Execute Command
        try:
            process = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "CHARM_INPUT_FILE": input_path},
            )

            stdout_lines = []
            stderr_lines = []

            # Stream output in real-time
            def read_stream(stream, collection, is_err=False):
                for line in stream:
                    collection.append(line)
                    print(line, end="")

            t_out = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
            t_err = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines))

            t_out.start()
            t_err.start()

            process.wait()
            t_out.join()
            t_err.join()

            if process.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Process exited with code {process.returncode}",
                    "stderr": "".join(stderr_lines),
                }

            # 3. Retrieve Output
            return {
                "status": "success",
                "output": "".join(stdout_lines),
                "message": "Process execution finished.",
            }

        except Exception as e:
            logger.error(f"Process Execution Error: {e}")
            return {"status": "error", "message": str(e)}
