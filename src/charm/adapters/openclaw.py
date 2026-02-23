import json
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

from ..contracts.uac import CharmConfig
from ..core.io import CharmEmitter
from ..core.logger import logger
from .base import BaseAdapter


class CharmOpenClawAdapter(BaseAdapter):
    """
    Adapter for the OpenClaw Host (MCP Client) with Cloud Persistence Support.
    It manages the lifecycle of the OpenClaw process, translates Charm Skills into
    MCP Server configurations, and bridges the I/O between Charm and OpenClaw.
    """

    def __init__(self, config: CharmConfig):
        super().__init__(None)
        self.config = config
        self.work_dir = os.getcwd()  # Directory where code is located (/app/agent_code)

        # --- [1. Persistence Strategy] ---
        # Must use CHARM_WORKSPACE_DIR passed by Runner (corresponds to GCS mount point)
        self.workspace_dir = os.getenv("CHARM_WORKSPACE_DIR")

        # Fallback for local development compatibility
        if not self.workspace_dir:
            self.workspace_dir = os.path.join(self.work_dir, "workspace")

        try:
            os.makedirs(self.workspace_dir, exist_ok=True)
            logger.info(f"📁 Persistence Active. Workspace: {self.workspace_dir}")
        except Exception as e:
            logger.warning(f"Failed to create persistence path: {e}")

        # Standard OpenClaw memory file
        self.memory_file = os.path.join(self.workspace_dir, "MEMORY.md")

    def _install_dependencies(self, skill_path: str):
        """
        [Auto-Dependency] Detects and installs deps for local skills.
        This runs every boot because container system-libs are ephemeral.
        """
        skill_name = os.path.basename(skill_path)

        # 1. Python Requirements
        req_file = os.path.join(skill_path, "requirements.txt")
        if os.path.exists(req_file):
            logger.info(f"📦 [{skill_name}] Installing Python dependencies...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", req_file],
                    stdout=subprocess.DEVNULL,  # Keep logs clean
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError:
                logger.error(f"❌ [{skill_name}] Failed to install requirements.txt")

        # 2. Node.js Packages
        pkg_file = os.path.join(skill_path, "package.json")
        if os.path.exists(pkg_file):
            # Check if node_modules already exists (optimization)
            if not os.path.exists(os.path.join(skill_path, "node_modules")):
                logger.info(f"📦 [{skill_name}] Installing Node.js dependencies...")
                try:
                    subprocess.check_call(
                        ["npm", "install", "--production", "--no-audit", "--no-fund"],
                        cwd=skill_path,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                    )
                except subprocess.CalledProcessError:
                    logger.error(f"❌ [{skill_name}] Failed to install npm packages")

    def _generate_openclaw_config(self) -> str:
        """
        Transform 'charm.yaml' into 'openclaw_config.json'.
        """
        mcp_servers = {}
        oc_config = self.config.runtime.config

        # Logic for writing IDENTITY.md, adding file existence check to avoid overwriting user customizations
        if oc_config and oc_config.system_prompt:
            identity_path = os.path.join(self.workspace_dir, "IDENTITY.md")
            try:
                if not os.path.exists(identity_path):
                    with open(identity_path, "w", encoding="utf-8") as f:
                        f.write(oc_config.system_prompt)
                    logger.info(f"🧠 System Prompt injected into {identity_path}")
            except Exception as e:
                logger.error(f"Failed to write IDENTITY.md: {e}")

        # Process Skills
        if self.config.runtime.skills:
            for skill in self.config.runtime.skills:
                server_config = {}
                is_local_path = False
                target_path = ""

                # --- Path Resolution ---
                if skill.source.startswith("local:"):
                    rel_path = skill.source.replace("local:", "")
                    target_path = os.path.abspath(rel_path)
                    is_local_path = True
                elif skill.source.startswith("git:") or skill.source.startswith("http"):
                    target_path = os.path.abspath(f"skills/{skill.name}")
                    is_local_path = True

                # --- Configuration Building ---
                if is_local_path:
                    if not os.path.exists(target_path):
                        logger.warning(f"⚠️ Skill path missing: {target_path}")
                        continue

                    # Auto-Install Deps
                    if not oc_config or oc_config.auto_install_dependencies:
                        self._install_dependencies(target_path)

                    # Detect Runtime
                    if os.path.isfile(target_path):
                        if target_path.endswith(".py"):
                            server_config = {"command": "python", "args": [target_path]}
                        elif target_path.endswith(".js"):
                            server_config = {"command": "node", "args": [target_path]}
                    else:
                        if os.path.exists(os.path.join(target_path, "package.json")):
                            server_config = {
                                "command": "npm",
                                "args": ["start"],
                                "cwd": target_path,
                            }
                        elif os.path.exists(os.path.join(target_path, "pyproject.toml")):
                            server_config = {
                                "command": "uv",
                                "args": ["run", "python", "-m", "server"],
                                "cwd": target_path,
                            }
                            if os.path.exists(os.path.join(target_path, "server.py")):
                                server_config["args"] = ["run", "python", "server.py"]
                        else:
                            server_config = {
                                "command": "python",
                                "args": [os.path.join(target_path, "server.py")],
                            }

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

                elif skill.source.startswith("pip:") or skill.source.startswith("pypi:"):
                    pkg_name = skill.source.replace("pip:", "").replace("pypi:", "")
                    server_config = {"command": "uvx", "args": [pkg_name]}

                # --- Environment Injection ---
                if server_config:
                    env_vars = skill.config.copy() if skill.config else {}
                    for env_key, env_value in os.environ.items():
                        if (
                            env_key.endswith("_API_KEY")
                            or env_key.endswith("_ACCESS_TOKEN")
                            or env_key.endswith("_TOKEN")
                            or env_key in ["OPENAI_API_BASE", "OPENAI_API_HOST"]
                        ):
                            if env_key not in env_vars:
                                env_vars[env_key] = env_value

                    if env_vars:
                        server_config["env"] = env_vars

                    mcp_servers[skill.name] = server_config

        # Restore LLM parameter assembly
        full_config = {
            "mcpServers": mcp_servers,
            "workspace": self.workspace_dir,
            "llm": {
                "model": oc_config.model if oc_config else "gpt-4o",
                "temperature": oc_config.temperature if oc_config else 0.0,
            },
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
        """Parse OpenClaw stdout to Charm Events."""
        clean_line = line.strip()
        if not clean_line:
            return

        # Extract thoughts, tool calls, and generated artifacts
        if re.match(r"^(Thought|Plan|Reasoning):", clean_line, re.IGNORECASE):
            content = clean_line.split(":", 1)[1].strip()
            CharmEmitter.emit_thinking(content)
        elif re.match(r"^(Calling|Executing|Tool):", clean_line, re.IGNORECASE):
            CharmEmitter.emit_thinking(f"🛠️ {clean_line}")
        elif "Created artifact:" in clean_line:
            match = re.search(r"Created artifact:\s*(.+)", clean_line)
            if match:
                path = match.group(1).strip()
                name = os.path.basename(path)
                CharmEmitter.emit_artifact(name=name, url=path, mime="auto")
        elif "Error:" in clean_line or "Exception" in clean_line:
            if "DeprecationWarning" not in clean_line:
                CharmEmitter.emit_error(clean_line)
        else:
            logger.debug(f"[OpenClaw] {clean_line}")

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info("🚀 Booting OpenClaw Adapter (Session Mode)")

        # 1. Copy initial templates (with non-overwriting mechanism)
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

        # 2. Config Generation
        config_path = self._generate_openclaw_config()

        # 3. Prepare Prompt (Normal or Upgrade Mode)
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
            # Filter out underlying system parameters to avoid interfering with AI
            for k, v in inputs.items():
                if k not in ["input", "__charm_thread_id__", "__charm_state__"]:
                    user_input += f"\n\n[{k}]: {v}"

        # 4. Start OpenClaw CLI
        cmd = ["openclaw", "run", "--config", config_path, "--prompt", user_input]

        env = os.environ.copy()
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

        # Ensure stdout collection array exists, used as fallback for Final Answer
        stdout_lines = []
        final_output = ""

        # Define Stream Reader
        def read_stream(stream, is_stderr):
            nonlocal final_output
            for line in stream:
                if not is_stderr:
                    if "Final Answer:" in line:
                        final_output = line.split("Final Answer:", 1)[1].strip()
                    else:
                        stdout_lines.append(line)

                self._parse_log(line)

        t_out = threading.Thread(target=read_stream, args=(process.stdout, False))
        t_err = threading.Thread(target=read_stream, args=(process.stderr, True))

        t_out.start()
        t_err.start()

        process.wait()
        t_out.join()
        t_err.join()

        if process.returncode != 0:
            return {"status": "error", "message": f"OpenClaw exited with code {process.returncode}"}

        # If Agent forgot to output Final Answer, backtrack and extract from log array
        if not final_output and stdout_lines:
            clean_output = [
                line for line in stdout_lines if not line.startswith("[") and "Thought:" not in line
            ]
            if clean_output:
                final_output = "\n".join(clean_output[-10:])

        return {
            "status": "success",
            "output": final_output or "Task completed successfully.",
            "charm_state": "",
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
