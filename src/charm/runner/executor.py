import base64
import json
import logging
import mimetypes
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
    ) -> str:
        # 1. Environment Variables
        env_file_lines = []
        for k, v in env_vars.items():
            safe_val = str(v).replace("\n", "\\n").replace('"', '\\"')
            env_file_lines.append(f'{k}="{safe_val}"')
        b64_env_content = base64.b64encode("\n".join(env_file_lines).encode()).decode()

        # 2. File Downloads
        dl_cmds = []
        if file_urls:
            for f, u in file_urls.items():
                dl_cmds.append(f"curl -s -L {shlex.quote(u)} -o {shlex.quote(os.path.basename(f))}")
        dl_block = "\n".join(dl_cmds) if dl_cmds else "true"

        # 3. Local SDK Install (Dev Only)
        install_local_sdk_cmd = ""
        if local_sdk_path and use_local_mount:
            install_local_sdk_cmd = f"""
            if [ -d "/mnt/local_sdk" ]; then
                echo '{EVENT_PREFIX}{{"type":"status","content":"[DEV] Installing Local SDK..."}}'
                uv pip install -e /mnt/local_sdk
            fi
            """

        # 4. Source Code Setup
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

        # 5. Dependency Installation Logic (Polyglot)

        # Node.js Dependencies
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

        # Python Dependencies
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

        # 6. Execution Command Selection
        if adapter_type == "node":
            # Node Execution Path
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Starting Node.js Agent..."}'
            npm start
            """
        elif use_file_input:
            # Python File Input Path (Docker Optimized)
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Running Agent (File Mode)..."}'
            python3 -c "import sys, subprocess, pathlib; \
            json_payload = pathlib.Path('/app/artifacts_mount/input.json').read_text(encoding='utf-8'); \
            sys.exit(subprocess.run(['charm', 'run', '.', '--json', json_payload]).returncode)"
            """
        else:
            # Python Cloud Run Fallback
            b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()
            execution_cmd = f"""
            echo '::CHARM_EVENT::{{"type":"status","content":"Running Agent (Cloud Mode)..."}}'
            INPUT_JSON="$(echo {b64_payload} | base64 -d)"
            charm run . --json "$INPUT_JSON"
            """

        # 7. Cleanup & Persistence Logic
        cleanup_function = """
        function cleanup {
            EXIT_CODE=$?
            echo '::CHARM_EVENT::{"type":"status","content":"Saving Execution Context..."}'
            
            # (A) Cloud Upload
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

            # (B) Local Sync
            if [ -z "$CHARM_ARTIFACT_UPLOAD_URL" ] && [ -d "/app/artifacts_mount" ]; then
                [ -f "charm_memory.json" ] && cp charm_memory.json /app/artifacts_mount/ 2>/dev/null
                
                find . -type f -newer .charm_snapshot \
                    -not -path "*/\\.*" \
                    -not -path "*/__pycache__/*" \
                    -not -path "*/node_modules/*" \
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
            
            echo "::CHARM_EVENT::{\"type\":\"internal_run_finished\",\"content\":{\"exit_code\":$EXIT_CODE}}"
        }
        trap cleanup EXIT
        """

        # 8. Assemble Final Script
        script = f"""
        set -e
        (while true; do echo '::CHARM_EVENT::{{"type":"thinking","content":"..."}}'; sleep 5; done) &
        HEARTBEAT_PID=$!
        
        {cleanup_function}
        
        trap "kill $HEARTBEAT_PID 2>/dev/null; cleanup" EXIT

        mkdir -p agent_code && cd agent_code

        {source_setup_block}

        # [TWEAK] Only check charm.yaml if not in node mode (optional policy)
        # [ ! -f charm.yaml ] && echo '{{EVENT_PREFIX}}{{"type":"error","content":"Missing charm.yaml"}}' && exit 1

        echo "{b64_env_content}" | base64 -d > .env
        {dl_block}

        # Memory File Setup
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
                try:
                    yield sse_pack("status", "Syncing Context to Cloud...")
                    memory_path = f"temp_memory/{run_id}.json"
                    supabase_client.storage.from_("agent_artifacts").upload(
                        memory_path,
                        json.dumps(history, ensure_ascii=False).encode("utf-8"),
                        {"content-type": "application/json", "upsert": "true"},
                    )
                    res = supabase_client.storage.from_("agent_artifacts").create_signed_url(
                        memory_path, 600
                    )
                    signed_url = res.get("signedURL") if isinstance(res, dict) else res.signedURL
                    file_urls[memory_file_name] = signed_url
                except Exception as e:
                    logger.error(f"Cloud memory sync failed: {e}")

            try:
                with open(
                    os.path.join(host_artifact_path, memory_file_name), "w", encoding="utf-8"
                ) as f:
                    json.dump(history, f, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Local memory write failed: {e}")

        artifact_upload_url = ""
        if self.env == "production" and supabase_client:
            try:
                artifact_path = f"{agent_id}/{run_id}/output_artifacts.tar.gz"
                res = supabase_client.storage.from_("agent_artifacts").create_signed_upload_url(
                    artifact_path
                )
                if res and "signedUrl" in res:
                    artifact_upload_url = res["signedUrl"]
                    env_vars["CHARM_ARTIFACT_UPLOAD_URL"] = artifact_upload_url
            except Exception as e:
                logger.error(f"Failed to generate artifact upload URL: {e}")

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
