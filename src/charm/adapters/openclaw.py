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
        self.config: CharmConfig = config
        self.work_dir = os.getcwd()  # Directory where code is located (/app/agent_code)

        # --- [1. Persistence Strategy] ---
        # Must use CHARM_WORKSPACE_DIR passed by Runner (corresponds to GCS mount point)
        self.workspace_dir: str = os.getenv("CHARM_WORKSPACE_DIR") or ""

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

    @staticmethod
    def _is_container_runtime() -> bool:
        """True when executing inside runner/Docker (not local `charm run`)."""
        return bool(
            os.getenv("CHARM_AGENT_ID")
            or os.getenv("CHARM_LIFECYCLE")
            or os.path.exists("/.dockerenv")
        )

    @staticmethod
    def _resolve_home(env: dict) -> str:
        """Use /root in containers; the real user home for local CLI runs."""
        if CharmOpenClawAdapter._is_container_runtime():
            return env.get("HOME") or "/root"
        return os.path.expanduser("~")

    @staticmethod
    def _openclaw_home(env: dict) -> str:
        return os.path.join(CharmOpenClawAdapter._resolve_home(env), ".openclaw")

    def _install_dependencies(self, skill_path: str):
        """
        [Auto-Dependency] Detects and installs deps for local skills.
        This runs every boot because container system-libs are ephemeral.
        """
        skill_name = os.path.basename(skill_path)

        # 1. Python Requirements
        req_file = os.path.join(skill_path, "requirements.txt")
        marker_file = os.path.join(skill_path, ".charm_installed")
        if os.path.exists(req_file) and not os.path.exists(marker_file):
            logger.info(f"📦 [{skill_name}] Installing Python dependencies...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", req_file],
                    stdout=subprocess.DEVNULL,  # Keep logs clean
                    stderr=subprocess.STDOUT,
                )
                with open(marker_file, "w") as f:
                    f.write("installed")
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

    def _onboard_openclaw(self, env: dict):
        """
        Run OpenClaw onboarding if not already initialized.
        Creates ~/.openclaw/openclaw.json with default config.
        """
        openclaw_home = self._openclaw_home(env)
        config_file = os.path.join(openclaw_home, "openclaw.json")

        if os.path.exists(config_file):
            return

        os.makedirs(openclaw_home, exist_ok=True)

        if not shutil.which("openclaw"):
            logger.warning(
                "openclaw CLI not found in PATH — writing minimal openclaw.json. "
                "Install with: npm install -g openclaw@latest"
            )
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
            return

        logger.info("Running OpenClaw onboarding (first boot)...")
        try:
            result = subprocess.run(
                [
                    "openclaw",
                    "onboard",
                    "--non-interactive",
                    "--accept-risk",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.debug(f"Onboard stderr (non-fatal): {result.stderr.strip()}")
            if not os.path.exists(config_file):
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            logger.info("OpenClaw onboarding complete.")
        except Exception as e:
            logger.warning(f"Onboarding issue (may be non-fatal): {e}")
            if not os.path.exists(config_file):
                try:
                    with open(config_file, "w", encoding="utf-8") as f:
                        json.dump({}, f)
                except OSError as write_err:
                    logger.error(f"Failed to create fallback openclaw.json: {write_err}")

    def _build_mcp_servers(self) -> dict:
        """
        Build MCP server configurations from charm.yaml skills.
        Returns a dict suitable for ~/.openclaw/.mcp.json
        """
        mcp_servers: Dict[str, Dict[str, Any]] = {}
        oc_config = self.config.runtime.config

        if not self.config.runtime.skills:
            return mcp_servers

        for skill in self.config.runtime.skills:
            server_config: Dict[str, Any] = {}
            is_local_path = False
            target_path = ""

            if skill.source.startswith("local:"):
                rel_path = skill.source.replace("local:", "")
                target_path = os.path.abspath(rel_path)
                is_local_path = True
            elif skill.source.startswith("git:") or skill.source.startswith("http"):
                target_path = os.path.abspath(f"skills/{skill.name}")
                is_local_path = True

            if is_local_path:
                if not os.path.exists(target_path):
                    logger.warning(f"Skill path missing: {target_path}")
                    continue

                if not oc_config or oc_config.auto_install_dependencies:
                    self._install_dependencies(target_path)

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

        return mcp_servers

    def _inject_proxy_env(self, env: dict):
        """Ensure both OPENAI_API_BASE and OPENAI_BASE_URL are set consistently.

        resolve_dependencies (main.py) already maps CHARM_LLM_PROXY_BASE →
        OPENAI_API_BASE before the container starts. We just make sure litellm's
        alternate env var name is also populated so nothing falls through.
        """
        proxy_base = env.get("OPENAI_API_BASE", "").strip()
        if proxy_base:
            env["OPENAI_BASE_URL"] = proxy_base
            logger.info(f"🔀 LLM proxy active: {proxy_base}")
        else:
            logger.warning("OPENAI_API_BASE not set — LLM calls may hit provider directly")

    def _generate_openclaw_config(self, env: dict):
        """Configure OpenClaw for the current session."""
        oc_config = self.config.runtime.config
        openclaw_home = self._openclaw_home(env)

        if oc_config and oc_config.system_prompt:
            identity_path = os.path.join(self.workspace_dir, "IDENTITY.md")
            try:
                if not os.path.exists(identity_path):
                    with open(identity_path, "w", encoding="utf-8") as f:
                        f.write(oc_config.system_prompt)
                    logger.info(f"🧠 System Prompt injected into {identity_path}")
            except Exception as e:
                logger.error(f"Failed to write IDENTITY.md: {e}")

        mcp_servers = self._build_mcp_servers()
        mcp_json_path = os.path.join(openclaw_home, ".mcp.json")
        try:
            os.makedirs(openclaw_home, exist_ok=True)
            with open(mcp_json_path, "w", encoding="utf-8") as f:
                json.dump(mcp_servers, f, indent=2)
            logger.info(f"MCP config written: {mcp_json_path} ({len(mcp_servers)} servers)")
        except Exception as e:
            logger.error(f"Failed to write .mcp.json: {e}")
            raise e

        # Read proxy config directly from the runner's env vars.
        # The runner sets CHARM_LLM_PROXY_BASE and CHARM_LLM_PROXY_KEY.
        # env is os.environ.copy() so these are available directly.
        proxy_base = env.get("CHARM_LLM_PROXY_BASE", "").strip()
        proxy_key = env.get("CHARM_LLM_PROXY_KEY", "").strip()

        raw_model = oc_config.model if oc_config else "gpt-4o"
        # Strip any existing provider prefix to obtain the bare model id
        model_id = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model

        if not proxy_base or not proxy_key:
            logger.warning(
                "CHARM_LLM_PROXY_BASE or CHARM_LLM_PROXY_KEY not set — LLM calls may fail"
            )

        # Patch openclaw.json to route LLM calls through the Charm proxy.
        #
        # Strategy: load the onboard-generated config (which has all required gateway/
        # session fields), then merge our provider override so the "openai" provider
        # sends requests to proxy_base instead of api.openai.com.
        #
        # The config MUST include models.providers.openai.models (array) or OpenClaw
        # rejects the entire config as invalid. The proxy_key stored here is NOT used
        # for auth — auth-profiles.json is the authoritative credential store. Having
        # it here prevents OpenClaw's schema validation from rejecting the section.
        config_path = os.path.join(openclaw_home, "openclaw.json")
        try:
            os.makedirs(openclaw_home, exist_ok=True)

            # Load the onboard-generated config (standard JSON written by _onboard_openclaw)
            base_cfg: dict = {}
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    base_cfg = json.load(f)
            except Exception:
                pass  # File absent or JSON5 — start fresh, will be minimal but valid

            # Deep-merge our proxy overrides into the base config
            base_cfg.setdefault("agents", {}).setdefault("defaults", {})["model"] = {
                "primary": f"openai/{model_id}"
            }
            base_cfg.setdefault("models", {}).setdefault("providers", {})["openai"] = {
                "baseUrl": proxy_base,
                "apiKey": proxy_key,
                "models": [{"id": model_id, "name": model_id}],
            }

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(base_cfg, f, indent=2)
            logger.info(f"✅ openclaw.json patched: model=openai/{model_id} → {proxy_base}")
        except Exception as e:
            logger.warning(f"Failed to patch openclaw.json: {e}")

        # Write auth-profiles.json for the 'main' agent so OpenClaw's per-agent
        # auth store is pre-populated.
        #
        # Correct AuthProfileStore format (from OpenClaw SDK types):
        #   version: 1 (required)
        #   profiles.<profileId>.type: "api_key"
        #   profiles.<profileId>.provider: "<provider>"
        #   profiles.<profileId>.key: "<raw api key>"  ← "key" NOT "apiKey"
        # Profile ID convention: "<provider>:api" (e.g. "openai:api")
        auth_dir = os.path.join(openclaw_home, "agents", "main", "agent")
        auth_path = os.path.join(auth_dir, "auth-profiles.json")
        try:
            os.makedirs(auth_dir, exist_ok=True)
            auth_profiles: dict = {
                "version": 1,
                "profiles": {
                    "openai:api": {
                        "type": "api_key",
                        "provider": "openai",
                        "key": proxy_key,
                    }
                },
            }
            with open(auth_path, "w", encoding="utf-8") as f:
                json.dump(auth_profiles, f, indent=2)
            logger.info(f"✅ auth-profiles.json written: {auth_path}")
        except Exception as e:
            logger.warning(f"Failed to write auth-profiles.json: {e}")

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

        env = os.environ.copy()
        env["HOME"] = self._resolve_home(env)
        self._inject_proxy_env(env)

        # During upgrades, the workspace should contain the user's customized files
        # from the PREVIOUS version (old bundle).  Seeding from agent_code/ (which
        # holds the NEW bundle) would cause the agentic merge to fail because the
        # diff expects the OLD content but the file already has the NEW content.
        #
        # In production the workspace is persisted (GCS Fuse), so old-version files
        # are already there.  For local Docker tests (no persistence) the workspace
        # starts empty — the agent uses the diff to create/update files from scratch.
        #
        # We only seed from bundle for normal (non-upgrade) runs where the workspace
        # is genuinely empty and needs bootstrapping.
        is_upgrade = "__charm_upgrade_diff__" in inputs

        if not is_upgrade:
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
        else:
            logger.info(
                "🔄 Upgrade mode: skipping workspace seed from bundle (workspace retains user's prior-version files)."
            )

        self._onboard_openclaw(env)
        self._generate_openclaw_config(env)

        if is_upgrade:
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
                template_str = "Execute upgrade with diff: {upgrade_diff}"

            user_input = template_str.format(upgrade_diff=upgrade_diff)
            logger.info("🔧 Upgrade payload intercepted. Launching Agentic Merge Mode.")
        else:
            user_input = str(inputs.get("input") or "")
            for k, v in inputs.items():
                if k not in [
                    "input",
                    "__charm_thread_id__",
                    "__charm_state__",
                    "history",
                    "messages",
                ]:
                    user_input += f"\n\n[{k}]: {v}"

        env["CHARM_WORKSPACE_DIR"] = self.workspace_dir
        
        # --- Memory Storage Plugin Sync (PRE-EXECUTION) ---
        from ..core.storage import StorageManager
        provider_name = "local"
        provider_config = {}
        if hasattr(self, "config") and self.config and hasattr(self.config, "memory"):
            provider_name = self.config.memory.provider
            provider_config = self.config.memory.config
            
        memory_store = StorageManager.get_provider(provider_name, provider_config)
        thread_id = inputs.get("__charm_thread_id__", "default")
        
        try:
            db_history = memory_store.load_messages(thread_id)
            if db_history and provider_name != "local":
                # Only write to MEMORY.md if using an external provider to inject DB state into OpenClaw
                with open(self.memory_file, "w", encoding="utf-8") as f:
                    for msg in db_history:
                        role = msg.get("role", "system").upper()
                        content = msg.get("content", "")
                        f.write(f"[{role}]: {content}\n\n")
        except Exception as e:
            logger.warning(f"Failed to sync memory from {provider_name}: {e}")
        # --------------------------------------------------

        cmd = [
            "openclaw",
            "agent",
            "--local",
            "--agent",
            "main",
            "--message",
            user_input,
            "--json",
        ]

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
                "message": (
                    "OpenClaw CLI not found in PATH. "
                    "Install with: npm install -g openclaw@latest"
                ),
            }

        stdout_lines = []
        stderr_lines = []
        final_output = ""

        def read_stream(stream, is_stderr):
            nonlocal final_output
            for line in stream:
                if is_stderr:
                    stderr_lines.append(line.strip())
                else:
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
            err_detail = "\n".join(stderr_lines[-20:]) if stderr_lines else "No stderr captured."
            logger.error(f"OpenClaw stderr:\n{err_detail}")
            return {
                "status": "error",
                "message": f"OpenClaw exited with code {process.returncode}\n{err_detail}",
            }

        if not final_output and stdout_lines:
            raw_output = "".join(stdout_lines).strip()
            try:
                result_json = json.loads(raw_output)
                # OpenClaw --json output: {"payloads": [{"text": "..."}], "meta": {...}, ...}
                if isinstance(result_json.get("payloads"), list):
                    texts = [p.get("text", "") for p in result_json["payloads"] if p.get("text")]
                    final_output = "\n".join(texts)
                else:
                    # Fallback for other potential JSON shapes
                    final_output = result_json.get("reply", result_json.get("output", ""))
            except (json.JSONDecodeError, TypeError):
                clean_output = [
                    line
                    for line in stdout_lines
                    if not line.startswith("[") and "Thought:" not in line
                ]
                if clean_output:
                    final_output = "\n".join(clean_output[-10:])

        # Emit upgrade sentinel to trigger version bump in runner
        if is_upgrade:
            final_output = f"UPGRADE_COMPLETE: {final_output}"

        output: str | Dict[str, Any] = final_output or "Task completed successfully."
        if isinstance(output, str) and "_charm_render_type" in output:
            try:
                parsed = json.loads(output)
                if isinstance(parsed, dict) and "_charm_render_type" in parsed:
                    output = parsed
            except json.JSONDecodeError:
                pass

        # --- Memory Storage Plugin Sync (POST-EXECUTION) ---
        try:
            if provider_name != "local" and os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    raw_memory = f.read()
                    
                # Store the updated raw memory as a single system message snapshot in the DB
                memory_store.save_messages(thread_id, [{"role": "system", "content": raw_memory}])
        except Exception as e:
            logger.warning(f"Failed to extract memory back to {provider_name}: {e}")
        # ---------------------------------------------------

        return {
            "status": "success",
            "output": output,
            "charm_state": "",
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
