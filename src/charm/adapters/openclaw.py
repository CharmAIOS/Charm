import json
import os
import re
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
        # OpenClaw is config-driven, so we initialize BaseAdapter with None for agent_instance
        super().__init__(None)
        self.config = config
        self.work_dir = os.getcwd()

        # Point the workspace to a persistent path within the container or a subdirectory of the current directory.
        # Ensure consistency with ENV OPENCLAW_WORKSPACE in the Dockerfile.
        self.openclaw_home = os.getenv("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        self.workspace_dir = os.getenv(
            "OPENCLAW_WORKSPACE", os.path.join(self.openclaw_home, "workspace")
        )

        # [Memory] Standard OpenClaw memory file
        self.memory_file = os.path.join(self.workspace_dir, "MEMORY.md")

    def _inject_memory(self, history: List[Dict[str, Any]]):
        """
        Inject Charm's user profile and conversation history into OpenClaw's long-term memory file.
        """
        try:
            if not os.path.exists(self.workspace_dir):
                os.makedirs(self.workspace_dir, exist_ok=True)

            # 1. Retrieve Global User Profile
            # This is typically fetched from the DB by the Runner and injected into environment variables.
            user_profile = os.getenv(
                "CHARM_USER_PROFILE", "User prefers concise and accurate answers."
            )

            # 2. Build Memory Content
            # OpenClaw reads this file as context upon startup.
            content = []
            content.append(f"# User Profile\n{user_profile}\n")

            if history:
                content.append("# Recent Context\n")
                # Retrieve the last 10 conversation turns to avoid exceeding the context window.
                for msg in history[-10:]:
                    role = msg.get("role", "unknown").upper()
                    text = msg.get("content", "")
                    content.append(f"- **{role}**: {text}")

            final_memory = "\n".join(content)

            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(final_memory)

            logger.info(f"Injected memory context into: {self.memory_file}")

        except Exception as e:
            logger.warning(f"Failed to inject memory: {e}")

    def _generate_openclaw_config(self) -> str:
        """
        Transform 'runtime.skills' from charm.yaml into a standard MCP Servers configuration file (JSON).
        """
        mcp_servers = {}

        if self.config.runtime.skills:
            for skill in self.config.runtime.skills:
                server_config = {}

                # --- A. Smithery / NPM Skills ---
                if skill.source.startswith("smithery:") or skill.source.startswith("npm:"):
                    pkg_name = skill.source.replace("smithery:", "").replace("npm:", "")
                    # Execute using npx (ensure @smithery/cli is installed or successfully downloaded).
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

                # --- B. Python / PyPI Skills ---
                elif skill.source.startswith("pip:") or skill.source.startswith("pypi:"):
                    pkg_name = skill.source.replace("pip:", "").replace("pypi:", "")
                    # Execute using uvx (uv tool run) for speed and isolation.
                    server_config = {"command": "uvx", "args": [pkg_name]}

                # --- C. Local Skills (Repositories) ---
                elif skill.source.startswith("local:"):
                    # The Executor links the skill to the current directory in Phase 3.
                    # Example path: local:./skills/browser-use -> ./skills/browser-use
                    rel_path = skill.source.replace("local:", "")
                    abs_path = os.path.abspath(rel_path)

                    if not os.path.exists(abs_path):
                        logger.warning(f"Skill path not found: {abs_path}")
                        continue

                    # Automatically detect startup method.
                    if os.path.isfile(abs_path):
                        # Targeted at a single file.
                        if abs_path.endswith(".py"):
                            server_config = {"command": "python", "args": [abs_path]}
                        elif abs_path.endswith(".js"):
                            server_config = {"command": "node", "args": [abs_path]}
                    else:
                        # Targeted at a directory, check for common entry points.
                        if os.path.exists(os.path.join(abs_path, "pyproject.toml")):
                            # Python project, use uv run.
                            server_config = {
                                "command": "uv",
                                "args": [
                                    "run",
                                    "python",
                                    "-m",
                                    "server",
                                ],  # Assumes module name is 'server'.
                                "cwd": abs_path,  # Set working directory.
                            }
                        elif os.path.exists(os.path.join(abs_path, "package.json")):
                            # Node project.
                            server_config = {"command": "npm", "args": ["start"], "cwd": abs_path}
                        else:
                            # Fallback: Try executing server.py.
                            server_config = {
                                "command": "python",
                                "args": [os.path.join(abs_path, "server.py")],
                            }

                # --- Auth & Env Injection ---
                # Convert configs defined in charm.yaml to environment variables.
                env_vars = skill.config.copy() if skill.config else {}

                # Automatically inject global API Keys (if present in environment variables).
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
            # Expand here based on charm.yaml, e.g., specifying the model:
            # "llm": { "model": "claude-3-5-sonnet-latest" }
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

        # [Log Type 1] Thinking / Planning
        # OpenClaw output example: "Thought: I need to use google-search..."
        if re.match(r"^(Thought|Plan|Reasoning):", clean_line, re.IGNORECASE):
            content = clean_line.split(":", 1)[1].strip()
            CharmEmitter.emit_thinking(content)

        # [Log Type 2] Tool Execution
        # OpenClaw output example: "Calling tool 'google-search' with args..."
        elif re.match(r"^(Calling|Executing|Tool):", clean_line, re.IGNORECASE):
            CharmEmitter.emit_thinking(f"🛠️ {clean_line}")

        # [Log Type 3] Artifact Generation
        # Assume OpenClaw output: "Created artifact: /path/to/file.pdf"
        elif "Created artifact:" in clean_line:
            match = re.search(r"Created artifact:\s*(.+)", clean_line)
            if match:
                path = match.group(1).strip()
                name = os.path.basename(path)
                # Use mime="auto" to let the Runner determine automatically.
                CharmEmitter.emit_artifact(name=name, url=path, mime="auto")

        # [Log Type 4] Errors
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
        logger.info(" Booting OpenClaw Adapter...")

        # 1. Memory Injection
        self._inject_memory(inputs.get("__charm_history__", []))

        # 2. Config Generation
        config_path = self._generate_openclaw_config()

        # 3. Prepare User Input
        user_input = inputs.get("input", "")
        # If specific variables are injected, append to Prompt.
        for k, v in inputs.items():
            if k not in ["input", "__charm_history__"]:
                user_input += f"\n\n[{k}]: {v}"

        # 4. Start OpenClaw CLI
        # Use 'openclaw' command installed via npm install -g.
        # Mode: Single execution (exec / run).
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
                l for l in stdout_lines if not l.startswith("[") and "Thought:" not in l
            ]
            if clean_output:
                final_output = "\n".join(clean_output[-10:])  # Take the last 10 lines.

        return {
            "status": "success",
            "output": final_output or "Task completed successfully (check artifacts).",
            "charm_state": "",  # No State Snapshot yet.
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
