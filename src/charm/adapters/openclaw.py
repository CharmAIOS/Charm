import json
import os
import pkgutil
import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional

from ..contracts.uac import CharmConfig
from ..core.io import CharmEmitter
from ..core.logger import logger
from .base import BaseAdapter


class CharmOpenClawAdapter(BaseAdapter):
    """
    Adapter for the OpenClaw Host (MCP Client).
    It manages the lifecycle of the OpenClaw process, translates Charm Skills into
    MCP Server configurations, and bridges the I/O between Charm and OpenClaw.
    """

    def __init__(self, config: CharmConfig):
        super().__init__(None)
        self.config = config
        self.work_dir = os.getcwd()

        # Point the workspace to a persistent path.
        self.openclaw_home = os.getenv("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        self.workspace_dir = os.getenv(
            "OPENCLAW_WORKSPACE", os.path.join(self.openclaw_home, "workspace")
        )

        # Standard OpenClaw memory file
        self.memory_file = os.path.join(self.workspace_dir, "MEMORY.md")

    def _inject_memory(self, history: List[Dict[str, Any]]):
        """
        The Runner has externally generated MEMORY.md (containing User Profile).
        Here we only need to append the 'Recent Conversation Context'.
        """
        try:
            if not os.path.exists(self.workspace_dir):
                os.makedirs(self.workspace_dir, exist_ok=True)

            # Read existing MEMORY.md (pulled from DB by Runner)
            existing_content = ""
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    existing_content = f.read()

            # Build new Context (Short-term memory)
            context_str = ""
            if history:
                context_str += "\n\n# Recent Conversation Context (Ephemeral)\n"
                for msg in history[-10:]:
                    role = msg.get("role", "unknown").upper()
                    text = msg.get("content", "")
                    context_str += f"- **{role}**: {text}\n"

            # Write back to file: Keep long-term memory + append short-term Context
            final_content = existing_content + context_str

            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(final_content)

            logger.info(f"Appended short-term context to: {self.memory_file}")

        except Exception as e:
            logger.warning(f"Failed to inject memory context: {e}")

    def _generate_openclaw_config(self) -> str:
        """
        Transform 'runtime.skills' from charm.yaml into a standard MCP Servers configuration file (JSON).
        Now handles Git/Zip sources by resolving them to local paths.
        """
        mcp_servers = {}

        if self.config.runtime.skills:
            for skill in self.config.runtime.skills:
                server_config = {}

                # --- Normalization Logic ---
                # Check if this is a downloaded skill (Git/Zip) or a purely local one
                is_local_path = False
                target_path = ""

                if skill.source.startswith("local:"):
                    target_path = skill.source.replace("local:", "")
                    is_local_path = True
                elif skill.source.startswith("git:") or skill.source.startswith("http"):
                    # The Runner script has mounted these to ./skills/{name}
                    target_path = f"skills/{skill.name}"
                    is_local_path = True

                # --- 1. Path-based Skills (Local / Git / Zip) ---
                if is_local_path:
                    abs_path = os.path.abspath(target_path)

                    if not os.path.exists(abs_path):
                        logger.warning(f"Skill path not found (Execution might fail): {abs_path}")
                        continue

                    # Heuristic detection for execution method
                    if os.path.isfile(abs_path):
                        # Single file mode
                        if abs_path.endswith(".py"):
                            server_config = {"command": "python", "args": [abs_path]}
                        elif abs_path.endswith(".js"):
                            server_config = {"command": "node", "args": [abs_path]}
                    else:
                        # Directory mode
                        if os.path.exists(os.path.join(abs_path, "pyproject.toml")):
                            # Python project (use uv)
                            server_config = {
                                "command": "uv",
                                "args": ["run", "python", "-m", "server"],  # Default assumption
                                "cwd": abs_path,
                            }
                            # Check if main.py or server.py exists to be more specific
                            if os.path.exists(os.path.join(abs_path, "server.py")):
                                server_config["args"] = ["run", "python", "server.py"]

                        elif os.path.exists(os.path.join(abs_path, "package.json")):
                            # Node project
                            server_config = {"command": "npm", "args": ["start"], "cwd": abs_path}
                        else:
                            # Fallback: Try server.py
                            server_config = {
                                "command": "python",
                                "args": [os.path.join(abs_path, "server.py")],
                            }

                # --- 2. Smithery / NPM Skills ---
                elif skill.source.startswith("smithery:") or skill.source.startswith("npm:"):
                    pkg_name = skill.source.replace("smithery:", "").replace("npm:", "")
                    server_config = {
                        "command": "npx",
                        "args": [
                            "-y",
                            "@smithery/cli",
                            "run",
                            pkg_name,
                            "--config",
                            json.dumps(skill.config),
                        ],
                    }

                # --- 3. Python / PyPI Skills ---
                elif skill.source.startswith("pip:") or skill.source.startswith("pypi:"):
                    pkg_name = skill.source.replace("pip:", "").replace("pypi:", "")
                    server_config = {"command": "uvx", "args": [pkg_name]}

                # --- Common Config Injection (Env & Auth) ---
                if server_config:
                    env_vars = skill.config.copy() if skill.config else {}

                    # Inject Global API Keys if present
                    for key in [
                        "OPENAI_API_KEY",
                        "ANTHROPIC_API_KEY",
                        "TAVILY_API_KEY",
                        "GOOGLE_API_KEY",
                    ]:
                        if key not in env_vars and os.environ.get(key):
                            env_vars[key] = os.environ[key]

                    if env_vars:
                        server_config["env"] = env_vars

                    mcp_servers[skill.name] = server_config

        # Build complete configuration
        full_config = {
            "mcpServers": mcp_servers,
            "workspace": self.workspace_dir,
        }

        config_path = os.path.join(self.work_dir, "openclaw_runtime_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)
            logger.info(f"Generated OpenClaw Config: {config_path}")
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            raise e

        return config_path

    def _parse_log(self, line: str):
        """
        Parse OpenClaw's stdout/stderr and convert into Charm UI events.
        Regex requires adjustment based on actual OpenClaw output.
        """
        clean_line = line.strip()
        if not clean_line:
            return

        # Thinking / Planning
        if re.match(r"^(Thought|Plan|Reasoning):", clean_line, re.IGNORECASE):
            content = clean_line.split(":", 1)[1].strip()
            CharmEmitter.emit_thinking(content)

        # Tool Execution
        elif re.match(r"^(Calling|Executing|Tool):", clean_line, re.IGNORECASE):
            CharmEmitter.emit_thinking(f"🛠️ {clean_line}")

        # Artifact Generation
        elif "Created artifact:" in clean_line:
            match = re.search(r"Created artifact:\s*(.+)", clean_line)
            if match:
                path = match.group(1).strip()
                name = os.path.basename(path)
                # Use mime="auto" to let the Runner determine automatically.
                CharmEmitter.emit_artifact(name=name, url=path, mime="auto")

        # Errors
        elif "Error:" in clean_line or "Exception" in clean_line:
            # Filter out noise warnings.
            if "DeprecationWarning" not in clean_line:
                CharmEmitter.emit_error(clean_line)

        else:
            # Log other messages as debug logs.
            logger.debug(f"[OpenClaw] {clean_line}")

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info("🚀 Booting OpenClaw Adapter (Session Mode)")

        try:
            for item in os.listdir(self.work_dir):
                if item in ["openclaw_runtime_config.json", "input.json"]:
                    continue

                if item.endswith(".md") or item.endswith(".txt") or item.endswith(".json"):
                    src_path = os.path.join(self.work_dir, item)
                    dst_path = os.path.join(self.workspace_dir, item)

                    if os.path.isfile(src_path):
                        if not os.path.exists(dst_path):
                            shutil.copy2(src_path, dst_path)
                            logger.info(f"📄 Initialized asset in workspace: {item}")
                        else:
                            logger.debug(f"📄 Asset {item} already exists, skipping overwrite.")
        except Exception as e:
            logger.error(f"Failed to sync static assets: {e}")

        # Config Generation
        config_path = self._generate_openclaw_config()

        # 2. Prepare Prompt (Normal or Upgrade Mode)
        if "__charm_upgrade_diff__" in inputs:
            upgrade_diff = inputs.pop("__charm_upgrade_diff__")

            try:
                template_bytes = pkgutil.get_data("charm", "templates/upgrade_directive.txt")
                template_str = (
                    template_bytes.decode("utf-8")
                    if template_bytes
                    else "Execute upgrade with diff: {upgrade_diff}"
                )
            except Exception as e:
                logger.error(f"Failed to load upgrade template: {e}")
                template_str = "Execute upgrade with diff: {upgrade_diff}"  # Fallback

            user_input = template_str.format(upgrade_diff=upgrade_diff)
            logger.info("🔧 Upgrade payload intercepted. Launching Agentic Merge Mode.")
        else:
            user_input = inputs.get("input", "")
            # Append context if provided
            for k, v in inputs.items():
                if k not in ["input"]:
                    user_input += f"\n\n[{k}]: {v}"

        # Start OpenClaw CLI
        cmd = ["openclaw", "run", "--config", config_path, "--prompt", user_input]

        logger.info(f"Executing Command: {' '.join(cmd)}")

        # Copy environment variables to ensure API Keys are passed.
        env = os.environ.copy()
        # Force HOME to prevent failure in finding the .openclaw directory.
        env["HOME"] = "/root"

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "message": "OpenClaw binary not found. Is it installed in the Docker image?",
            }

        stdout_lines = []
        final_output = ""

        # Define Stream Reader
        def read_stream(stream, is_stderr):
            nonlocal final_output
            for line in stream:
                # Only stdout contains results; stderr is typically for logs.
                if not is_stderr:
                    # Simple heuristic: extract content following "Final Answer:".
                    if "Final Answer:" in line:
                        final_output = line.split("Final Answer:", 1)[1].strip()
                    else:
                        stdout_lines.append(line)

                # Unify log parsing and emit events.
                self._parse_log(line)

        # Dual-thread reading to prevent buffer overflow leading to Deadlock.
        t_out = threading.Thread(target=read_stream, args=(process.stdout, False))
        t_err = threading.Thread(target=read_stream, args=(process.stderr, True))

        t_out.start()
        t_err.start()

        process.wait()
        t_out.join()
        t_err.join()

        if process.returncode != 0:
            return {"status": "error", "message": f"OpenClaw exited with code {process.returncode}"}

        if not final_output and stdout_lines:
            # Filter out obvious log lines.
            clean_output = [
                line for line in stdout_lines if not line.startswith("[") and "Thought:" not in line
            ]
            if clean_output:
                final_output = "\n".join(clean_output[-10:])

        return {
            "status": "success",
            "output": final_output or "Task completed successfully (check artifacts).",
            "charm_state": "",  # No State Snapshot yet.
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
