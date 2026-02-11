import base64
import hashlib
import json
import logging
import os
import shlex
import shutil
import tempfile
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .backend.base import ExecutionBackend, RunConfig
from .backend.docker import DockerBackend
from .protocol import EVENT_PREFIX, sse_pack

try:
    from .backend.cloud_run import CloudRunBackend
except ImportError:
    CloudRunBackend = None

logger = logging.getLogger("charm.runner")

TEMP_DIR = tempfile.gettempdir()
HOST_CACHE_DIR = os.path.join(TEMP_DIR, "charm_uv_cache")
HOST_ARTIFACTS_ROOT = os.path.join(TEMP_DIR, "charm_artifacts_buffer")


class CharmDockerExecutor:
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")

        os.makedirs(HOST_CACHE_DIR, exist_ok=True)
        os.makedirs(HOST_ARTIFACTS_ROOT, exist_ok=True)

        if self.env in ["production", "staging"]:
            logger.info(f"Cloud Mode ({self.env}): Backend Selection Strategy Active")
            if CloudRunBackend:
                self.backend: ExecutionBackend = CloudRunBackend()
            else:
                logger.error("CloudRunBackend missing. Falling back to Docker.")
                self.backend = DockerBackend()
        else:
            logger.info("Development Mode: Using DockerBackend")
            self.backend = DockerBackend()

    def _calculate_skill_hash(self, source: str, version: str = "latest") -> str:
        """
        Calculate unique Hash for Skill, used for cache path.
        Same Source + Same Version = Same Hash (Cache Hit)
        """
        raw = f"{source}@{version}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def _generate_skill_install_block(self, skills: List[Dict[str, Any]]) -> str:
        """
        Generate Bash script block: handles cache checking, Skill installation, and linking.
        This is the core logic for realizing "Hot Update" and "Instant Open".
        """
        if not skills:
            return ""

        script_lines = [
            "\n# --- Dynamic Skill Loading System ---",
            "mkdir -p ./skills",
            f'echo \'{EVENT_PREFIX}{{"type":"status","content":"Checking Skill Cache..."}}\'',
        ]

        for skill in skills:
            name = skill.get("name")
            source = skill.get("source", "")
            version = skill.get("version", "latest")

            # Git Repositories (Smart Update Logic)
            if source.startswith("git:") or source.startswith("http"):
                repo_url = source.replace("git:", "")
                skill_hash = self._calculate_skill_hash(source, version)

                # Path definitions
                cache_path = f"/charm_cache/skills/{skill_hash}"
                local_link_path = f"./skills/{name}"

                # Check if it is a dynamic branch (main/master/latest)
                is_dynamic_branch = version in ["latest", "main", "master", ""]

                script_lines.append(f"\n# Skill (Git): {name}")

                # Download or Update Code
                script_lines.append(f"if [ -d '{cache_path}' ]; then")

                if is_dynamic_branch:
                    # Check only when specified as main/latest
                    # Fetch remote status
                    script_lines.append(f"    echo '⚡ Cache Hit. Checking for updates...'")
                    script_lines.append(f"    cd '{cache_path}'")
                    script_lines.append(f"    git fetch -q origin {version or 'HEAD'}")

                    # Compare Hash (Local vs Remote)
                    script_lines.append(
                        f'    if [ "$(git rev-parse HEAD)" != "$(git rev-parse FETCH_HEAD)" ]; then'
                    )
                    script_lines.append(f"        echo '🔄 New version detected. Updating...'")
                    script_lines.append(f"        git merge FETCH_HEAD -q")
                    script_lines.append(f"        UPDATED=1")
                    script_lines.append(f"    else")
                    script_lines.append(f"        echo '✅ Up to date. Skipping download.'")
                    script_lines.append(f"        UPDATED=0")
                    script_lines.append(f"    fi")
                    script_lines.append(f"    cd - > /dev/null")
                else:
                    # If pinned version, trust cache directly
                    script_lines.append(
                        f"    echo '⚡ Cache Hit (Pinned Version). Skipping checks.'"
                    )
                    script_lines.append(f"    UPDATED=0")

                script_lines.append(f"else")
                # Cache Miss: First download
                script_lines.append(f"    echo 'Installing Skill: {name}...'")
                script_lines.append(f"    git clone --depth 1 {repo_url} '{cache_path}'")
                script_lines.append(f"    UPDATED=1")
                script_lines.append(f"fi")

                # Smart Dependency Installation
                script_lines.append(f"if [ -f '{cache_path}/requirements.txt' ]; then")
                script_lines.append(
                    f"    REQ_HASH=$(md5sum '{cache_path}/requirements.txt' | awk '{{print $1}}')"
                )
                script_lines.append(
                    f"    INSTALLED_HASH=$(cat '/tmp/{name}_req.hash' 2>/dev/null || echo '')"
                )

                script_lines.append(
                    f'    if [ "$UPDATED" -eq 1 ] || [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then'
                )
                script_lines.append(
                    f"        echo '📦 Installing/Updating Python deps for {name}...'"
                )
                script_lines.append(f"        uv pip install -r '{cache_path}/requirements.txt'")
                script_lines.append(f"        echo \"$REQ_HASH\" > '/tmp/{name}_req.hash'")
                script_lines.append(f"    fi")
                script_lines.append(f"fi")

                # Node.js Dependencies
                script_lines.append(f"if [ -f '{cache_path}/package.json' ]; then")
                script_lines.append(
                    f"    if [ \"$UPDATED\" -eq 1 ] || [ ! -d '{cache_path}/node_modules' ]; then"
                )
                script_lines.append(f"        echo '📦 Check/Update Node deps for {name}...'")
                script_lines.append(
                    f"        cd '{cache_path}' && npm install --production --no-audit --quiet && cd -"
                )
                script_lines.append(f"    fi")
                script_lines.append(f"fi")

                # Linking
                script_lines.append(f"rm -rf '{local_link_path}'")
                script_lines.append(f"ln -s '{cache_path}' '{local_link_path}'")

            # NPM Skills
            elif source.startswith("smithery:") or source.startswith("npm:"):
                pkg_name = source.replace("smithery:", "").replace("npm:", "")
                script_lines.append(f"\n# Skill (NPM): {name}")
                script_lines.append(f"if command -v npm &> /dev/null; then")
                script_lines.append(f"    echo '📦 Pre-installing NPM Package: {pkg_name}...'")
                script_lines.append(f"    npm install -g {pkg_name} --quiet")
                script_lines.append(f"else")
                script_lines.append(
                    f"    echo '⚠️ Node.js not found. Skipping {name}. (Use Full Image)'"
                )
                script_lines.append(f"fi")

            # PyPI Skills
            elif source.startswith("pip:") or source.startswith("pypi:"):
                pkg_name = source.replace("pip:", "").replace("pypi:", "")
                script_lines.append(f"\n# Skill (PyPI): {name}")
                script_lines.append(f"echo '🐍 Pre-installing PyPI Package: {pkg_name}...'")
                script_lines.append(f"uv pip install {pkg_name}")

        return "\n".join(script_lines)

    def _generate_bash_script(
        self,
        bundle_url: str,
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        input_payload: Dict[str, Any],
        local_sdk_path: Optional[str] = None,
        use_local_mount: bool = False,
        use_file_input: bool = False,
        adapter_type: str = "python",
        skills: List[Dict[str, Any]] = [],
    ) -> str:
        # Environment Variables
        env_file_lines = []
        for k, v in env_vars.items():
            # Escape newlines and quotes to prevent bash errors
            safe_val = str(v).replace("\n", "\\n").replace('"', '\\"')
            env_file_lines.append(f'{k}="{safe_val}"')
        b64_env_content = base64.b64encode("\n".join(env_file_lines).encode()).decode()

        # File Downloads
        dl_cmds = []
        if file_urls:
            for f, u in file_urls.items():
                dl_cmds.append(f"curl -s -L {shlex.quote(u)} -o {shlex.quote(os.path.basename(f))}")
        dl_block = "\n".join(dl_cmds) if dl_cmds else "true"

        # Local SDK Install (Dev Only)
        install_local_sdk_cmd = ""
        if local_sdk_path and use_local_mount:
            install_local_sdk_cmd = f"""
            if [ -d "/mnt/local_sdk" ]; then
                echo '{EVENT_PREFIX}{{"type":"status","content":"[DEV] Installing Local SDK..."}}'
                uv pip install -e /mnt/local_sdk
            fi
            """

        # Source Code Setup
        if use_local_mount:
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Local Source Code..."}}'
            [ ! -d "/app/local_source_mount" ] && exit 1
            cp -rT /app/local_source_mount/. .
            """
        else:
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Downloading Bundle..."}}'
            curl -s -L {shlex.quote(bundle_url)} -o bundle.tar.gz
            tar -xzf bundle.tar.gz --no-same-owner && rm bundle.tar.gz
            """

        # Dependency Installation Logic (Polyglot)
        install_node_deps_block = """
        if [ -f "package.json" ]; then
            echo '::CHARM_EVENT::{"type":"status","content":"Installing Node.js dependencies..."}'
            # Prefer 'npm ci' if lockfile exists for speed/consistency
            if [ -f "package-lock.json" ]; then
                npm ci --quiet
            else
                npm install --no-audit --no-fund --quiet
            fi
        fi
        """

        install_python_deps_block = """
        if [ -f pyproject.toml ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing Python dependencies..."}}'
            uv pip install -q -r pyproject.toml || uv pip install -q .
        elif [ -f requirements.txt ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing Python dependencies..."}}'
            uv pip install -q -r requirements.txt
        fi
        """

        # SDK Setup
        sdk_install_block = """
        if python -c "import charm" 2>/dev/null; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Pre-installed Charm SDK."}}'
        else
            echo '{EVENT_PREFIX}{{"type":"status","content":"SDK not found. Installing from PyPI..."}}'
            uv pip install --upgrade "charmos[runner]>=0.4.20"
        fi
        """

        # Skill Installation Block
        skill_setup_block = self._generate_skill_install_block(skills)

        # Memory Hydration Block
        MEMORY_FILE_PATH = "/root/.openclaw/workspace/MEMORY.md"
        memory_hydration_block = f"""
        mkdir -p "$(dirname "{MEMORY_FILE_PATH}")"
        if [ ! -z "$CHARM_USER_PROFILE" ]; then
            echo "$CHARM_USER_PROFILE" > "{MEMORY_FILE_PATH}"
            echo '::CHARM_EVENT::{{"type":"status","content":"🧠 Memory Hydrated"}}'
        fi
        """

        # Execution Command Selection
        if adapter_type == "node":
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Starting Node.js Agent..."}'
            npm start
            """
        elif adapter_type == "openclaw":
            # OpenClaw Execution Path
            b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()
            execution_cmd = f"""
            echo '::CHARM_EVENT::{{"type":"status","content":"Booting OpenClaw Host..."}}'
            # Set UAC_SKILLS environment variable implied by charm.yaml mount logic
            INPUT_JSON="$(echo {b64_payload} | base64 -d)"
            # Launch using Charm SDK to load OpenClawAdapter.
            charm run . --json "$INPUT_JSON"
            """
        elif use_file_input:
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Running Agent (File Mode)..."}'
            python3 -c "import sys, subprocess, pathlib; \
            json_payload = pathlib.Path('/app/artifacts_mount/input.json').read_text(encoding='utf-8'); \
            sys.exit(subprocess.run(['charm', 'run', '.', '--json', json_payload]).returncode)"
            """
        else:
            b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()
            execution_cmd = f"""
            echo '::CHARM_EVENT::{{"type":"status","content":"Running Agent (Cloud Mode)..."}}'
            INPUT_JSON="$(echo {b64_payload} | base64 -d)"
            charm run . --json "$INPUT_JSON"
            """

        # Cleanup & Persistence Logic
        cleanup_function = f"""
        function cleanup {{
            EXIT_CODE=$?
            echo '::CHARM_EVENT::{{"type":"status","content":"Saving Execution Context..."}}'
            
            # --- 1. Memory Dehydration (Sync back to Store) ---
            # Checks if MEMORY.md exists and if we have the necessary credentials to sync.
            if [ -f "{MEMORY_FILE_PATH}" ] && [ ! -z "$CHARM_USER_ID" ] && [ ! -z "$CHARM_INTERNAL_SECRET" ]; then
                echo '::CHARM_EVENT::{{"type":"status","content":"🧠 Syncing Memory to Cloud..."}}'
                
                # Read content and base64 encode it to safely transmit via JSON
                MEM_B64=$(cat "{MEMORY_FILE_PATH}" | base64 -w 0)
                
                # Send POST request to Store API
                # CHARM_STORE_URL is injected by main.py
                curl -s -X POST \\
                     -H "Content-Type: application/json" \\
                     -H "Authorization: Bearer $CHARM_INTERNAL_SECRET" \\
                     -d "{{\\"user_id\\": \\"$CHARM_USER_ID\\", \\"memory_content_b64\\": \\"$MEM_B64\\"}}" \\
                     "$CHARM_STORE_URL/api/internal/sync-memory" || true
            fi

            # --- 2. Cloud Artifact Upload ---
            if [ ! -z "$CHARM_ARTIFACT_UPLOAD_URL" ]; then
                tar -czf output_artifacts.tar.gz \
                    --exclude='./.*' \
                    --exclude='__pycache__' \
                    --exclude='charm.yaml' \
                    --exclude='requirements.txt' \
                    --exclude='pyproject.toml' \
                    --exclude='node_modules' \
                    --exclude='*.py' \
                    --exclude='output_artifacts.tar.gz' \
                    --newer .charm_snapshot .

                curl -s -X PUT -T output_artifacts.tar.gz -H "Content-Type: application/gzip" "$CHARM_ARTIFACT_UPLOAD_URL"
            fi

            # --- 3. Local Artifact Sync (Dev Mode) ---
            if [ -z "$CHARM_ARTIFACT_UPLOAD_URL" ] && [ -d "/app/artifacts_mount" ]; then
                # Sync memory file locally for inspection
                if [ -f "$CHARM_MEMORY_FILE" ]; then 
                    cp "$CHARM_MEMORY_FILE" /app/artifacts_mount/ 2>/dev/null
                elif [ -f "charm_memory.json" ]; then
                    cp "charm_memory.json" /app/artifacts_mount/ 2>/dev/null
                fi
                
                # Sync OpenClaw memory
                if [ -f "{MEMORY_FILE_PATH}" ]; then
                     mkdir -p /app/artifacts_mount/.openclaw/workspace
                     cp "{MEMORY_FILE_PATH}" /app/artifacts_mount/MEMORY.md 2>/dev/null
                fi
                
                find . -type f -newer .charm_snapshot \
                    -not -path "*/\\.*" \
                    -not -path "*/__pycache__/*" \
                    -not -path "*/node_modules/*" \
                    -not -path "*/skills/*" \
                    -not -name ".charm_snapshot" \
                    -not -name "charm.yaml" \
                    -not -name "*.py" \
                    -not -name ".env" \
                    -not -name "charm_memory.json" \
                    > .charm_new_files

                while IFS= read -r file; do
                    [ -f "$file" ] && cp --parents "$file" /app/artifacts_mount/ 2>/dev/null || true
                done < .charm_new_files
            fi
            
            echo "::CHARM_EVENT::{{\\"type\\":\\"internal_run_finished\\",\\"content\\":{{\\"exit_code\\":$EXIT_CODE}}}}"
        }}
        trap cleanup EXIT
        """

        # Assemble Final Script
        script = f"""
        set -e
        (while true; do echo '::CHARM_EVENT::{{"type":"thinking","content":"..."}}'; sleep 5; done) &
        HEARTBEAT_PID=$!
        
        {cleanup_function}
        
        trap "kill $HEARTBEAT_PID 2>/dev/null; cleanup" EXIT

        mkdir -p agent_code && cd agent_code

        {source_setup_block}

        echo "{b64_env_content}" | base64 -d > .env
        {dl_block}

        # Memory File Setup (Chat History)
        if [ -f "charm_memory.json" ]; then
            export CHARM_MEMORY_FILE="$(pwd)/charm_memory.json"
        else
            export CHARM_MEMORY_FILE="/app/artifacts_mount/charm_memory.json"
        fi
        mkdir -p /app/artifacts_mount

        {install_local_sdk_cmd}

        # Install Dependencies
        {install_node_deps_block}
        {install_python_deps_block}
        
        # Install Skills (Dynamic Loading)
        {skill_setup_block}
        
        # Inject Global Memory (User Profile)
        {memory_hydration_block}

        # Config Runtime (Python only)
        if [ "{adapter_type}" != "node" ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Configuring Python Runtime..."}}'
            {sdk_install_block}
            export PYTHONPATH=$PYTHONPATH:$(pwd)
        fi
        
        # Snapshot for artifact diffing
        find . -type f > .charm_snapshot

        set +e
        export TERM=dumb 
        
        {execution_cmd}
        """
        return script

    async def run(
        self,
        agent_id: str,
        bundle_url: str,
        input_payload: Dict[str, Any],
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        history: List[Dict[str, str]],
        state_snapshot: str = "",
        local_source_path: Optional[str] = None,
        supabase_client: Any = None,
        image: Optional[str] = None,
        adapter_type: str = "python",
        skills: List[Dict[str, Any]] = [],
    ) -> AsyncGenerator[str, None]:
        run_timestamp = int(time.time())
        run_id = f"{agent_id}_{run_timestamp}"
        host_artifact_path = os.path.join(HOST_ARTIFACTS_ROOT, run_id)
        os.makedirs(host_artifact_path, exist_ok=True)

        if state_snapshot:
            input_payload["__charm_state__"] = state_snapshot

        memory_file_name = "charm_memory.json"
        if history:
            if self.env == "production" and supabase_client:
                pass

            try:
                with open(
                    os.path.join(host_artifact_path, memory_file_name), "w", encoding="utf-8"
                ) as f:
                    json.dump(history, f, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Local memory write failed: {e}")

        local_sdk_path = os.getenv("LOCAL_SDK_HOST_PATH")
        should_mount_local = bool(local_source_path) and isinstance(self.backend, DockerBackend)

        use_file_input = False
        if isinstance(self.backend, DockerBackend):
            try:
                input_path = os.path.join(host_artifact_path, "input.json")
                with open(input_path, "w", encoding="utf-8") as f:
                    json.dump(input_payload, f, ensure_ascii=False)
                use_file_input = True
                logger.info(f"Payload written to {input_path} for Docker mount.")
            except Exception as e:
                logger.error(f"Failed to write input.json: {e}")

        script_content = self._generate_bash_script(
            bundle_url=bundle_url,
            env_vars=env_vars,
            file_urls=file_urls,
            input_payload=input_payload,
            local_sdk_path=local_sdk_path,
            use_local_mount=should_mount_local,
            use_file_input=use_file_input,
            adapter_type=adapter_type,
            skills=skills,
        )

        config = RunConfig(
            agent_id=agent_id,
            run_id=run_id,
            bundle_url=bundle_url,
            input_payload=input_payload,
            env_vars=env_vars,
            file_urls=file_urls,
            script_content=script_content,
            host_artifact_path=host_artifact_path,
            host_cache_dir=HOST_CACHE_DIR,
            local_source_path=local_source_path if should_mount_local else None,
            image=image,
        )

        try:
            async for log in self.backend.stream_logs(config):
                if "internal_artifact_found" in log:
                    yield log
                    continue
                yield log

        except Exception as e:
            logger.exception("Orchestrator Error")
            yield sse_pack("error", f"Orchestrator Error: {e}")
        finally:
            await self.backend.cleanup(run_id)
            shutil.rmtree(host_artifact_path, ignore_errors=True)
