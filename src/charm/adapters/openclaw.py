import json
import os
import re
import subprocess
import threading
import sys
import shutil
from typing import Any, Dict, List, Optional

from ..contracts.uac import CharmConfig
from ..core.io import CharmEmitter
from ..core.logger import logger
from .base import BaseAdapter


class CharmOpenClawAdapter(BaseAdapter):
    """
    Adapter for the OpenClaw Host (MCP Client) with Cloud Persistence Support.
    """

    def __init__(self, config: CharmConfig):
        super().__init__(None)
        self.config = config
        self.work_dir = os.getcwd()  # 這是代碼所在的目錄 (/app/agent_code)

        # --- [1. Persistence Strategy] ---
        # Cloud Run Mount Path: /root/.openclaw (Mapped to GCS Bucket)
        # We enforce sub-directory isolation: /root/.openclaw/{user_id}/{agent_id}

        self.mount_root = "/root/.openclaw"
        self.user_id = os.getenv("CHARM_USER_ID", "local_dev")

        # Agent ID comes from YAML, default to uuid if missing
        self.agent_id = self.config.id or "default_agent"

        # The actual persistent home for THIS agent instance
        self.agent_home = os.path.join(self.mount_root, self.user_id, self.agent_id)
        self.workspace_dir = os.path.join(self.agent_home, "workspace")

        # Ensure directories exist (GCS Fuse creates folders on write)
        try:
            os.makedirs(self.workspace_dir, exist_ok=True)
            logger.info(f"📁 Persistence Active. Workspace: {self.workspace_dir}")
        except Exception as e:
            logger.warning(f"Failed to create persistence path (using tmp?): {e}")
            self.workspace_dir = os.path.join(self.work_dir, "workspace")

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
        oc_config = self.config.runtime.config  # The 'OpenClawConfig' object

        # Inject System Prompt if defined in YAML
        if oc_config and oc_config.system_prompt:
            identity_path = os.path.join(self.workspace_dir, "IDENTITY.md")
            try:
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
                    # Relative to project root
                    rel_path = skill.source.replace("local:", "")
                    target_path = os.path.abspath(rel_path)
                    is_local_path = True

                elif skill.source.startswith("git:") or skill.source.startswith("http"):
                    # Downloaded by Executor to ./skills/{name}
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
                    if os.path.isfile(target_path) and target_path.endswith(".py"):
                        server_config = {"command": "python", "args": [target_path]}
                    elif os.path.isfile(target_path) and target_path.endswith(".js"):
                        server_config = {"command": "node", "args": [target_path]}
                    elif os.path.isdir(target_path):
                        # Directory Heuristics
                        if os.path.exists(os.path.join(target_path, "package.json")):
                            server_config = {
                                "command": "npm",
                                "args": ["start"],
                                "cwd": target_path,
                            }
                        elif os.path.exists(os.path.join(target_path, "pyproject.toml")):
                            # Use uv for speed if available
                            server_config = {
                                "command": "uv",
                                "args": ["run", "python", "-m", "server"],
                                "cwd": target_path,
                            }
                        else:
                            # Fallback
                            server_config = {
                                "command": "python",
                                "args": [os.path.join(target_path, "server.py")],
                            }

                # ... (Registry/Smithery handling - Standard) ...
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

                # --- Environment Injection ---
                if server_config:
                    env_vars = skill.config.copy() if skill.config else {}
                    # Pass through global keys
                    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY"]:
                        if os.environ.get(key):
                            env_vars[key] = os.environ[key]

                    if env_vars:
                        server_config["env"] = env_vars

                    mcp_servers[skill.name] = server_config

        # Construct Final Config Payload
        full_config = {
            "mcpServers": mcp_servers,
            "workspace": self.workspace_dir,  # This is the magic GCS path
            "llm": {
                "model": oc_config.model if oc_config else "gpt-4o",
                "temperature": oc_config.temperature if oc_config else 0.0,
            },
        }

        config_path = os.path.join(self.work_dir, "openclaw_runtime_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(full_config, f, indent=2)

        return config_path

    def _parse_log(self, line: str):
        """Parse OpenClaw stdout to Charm Events."""
        clean = line.strip()
        if not clean:
            return

        if re.match(r"^(Thought|Plan|Reasoning):", clean, re.IGNORECASE):
            CharmEmitter.emit_thinking(clean.split(":", 1)[1].strip())
        elif "Error:" in clean:
            CharmEmitter.emit_error(clean)
        # Add more parsers as needed

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info("🚀 Booting OpenClaw Adapter (Session Mode)")

        # 1. Config Generation (This triggers dependency install)
        config_path = self._generate_openclaw_config()

        # 2. Prepare Prompt
        user_input = inputs.get("input", "")
        # Append context if provided
        for k, v in inputs.items():
            if k not in ["input", "__charm_history__", "user_profile"]:
                user_input += f"\n\n[{k}]: {v}"

        # 3. Launch OpenClaw
        cmd = ["openclaw", "run", "--config", config_path, "--prompt", user_input]

        # Ensure HOME is set correctly for tools that rely on it
        env = os.environ.copy()
        env["HOME"] = "/root"  # Standard for our container

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
            return {"status": "error", "message": "OpenClaw binary not found in container."}

        # ... (Output streaming logic remains same as previous version) ...
        # Simplified here for brevity, paste the threading logic from previous file

        final_output = ""

        def read_stream(stream, is_err):
            nonlocal final_output
            for line in stream:
                if not is_err and "Final Answer:" in line:
                    final_output = line.split("Final Answer:", 1)[1].strip()
                self._parse_log(line)

        t_out = threading.Thread(target=read_stream, args=(process.stdout, False))
        t_err = threading.Thread(target=read_stream, args=(process.stderr, True))
        t_out.start()
        t_err.start()
        process.wait()
        t_out.join()
        t_err.join()

        return {
            "status": "success",
            "output": final_output or "Task completed.",
            "charm_state": "",  # State is handled by GCS now
        }

    # ... (Stubs) ...
    def get_state(self):
        return {}

    def set_tools(self, tools):
        pass
