import os
import json
import base64
import time
import shutil
import tempfile
import logging
import shlex
import mimetypes
from typing import Any, AsyncGenerator, Dict, List, Optional

from .protocol import EVENT_PREFIX, sse_pack
from .backend.base import RunConfig, ExecutionBackend
from .backend.docker import DockerBackend

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

        if self.env == "production":
            logger.info("🚀 Production Mode: Backend Selection Strategy Active")
            if CloudRunBackend:
                self.backend: ExecutionBackend = CloudRunBackend()
            else:
                logger.error("❌ CloudRunBackend missing. Falling back to Docker.")
                self.backend = DockerBackend()
        else:
            logger.info("🛠️ Development Mode: Using DockerBackend")
            self.backend = DockerBackend()

    def _generate_bash_script(
        self,
        bundle_url: str,
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        input_payload: Dict[str, Any],
        local_sdk_path: Optional[str] = None,
        use_local_mount: bool = False,
    ) -> str:
        print(f"\n[DEBUG] Bundle URL sent to Cloud Run: {bundle_url}\n")

        env_file_lines = []
        for k, v in env_vars.items():
            safe_val = str(v).replace("\n", "\\n").replace('"', '\\"')
            env_file_lines.append(f'{k}="{safe_val}"')
        b64_env_content = base64.b64encode("\n".join(env_file_lines).encode()).decode()

        dl_cmds = []
        if file_urls:
            for f, u in file_urls.items():
                dl_cmds.append(f"curl -s -L {shlex.quote(u)} -o {shlex.quote(os.path.basename(f))}")
        dl_block = "\n".join(dl_cmds) if dl_cmds else "true"

        b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()

        install_local_sdk_cmd = ""
        if local_sdk_path and use_local_mount:
            install_local_sdk_cmd = f"""
            if [ -d "/mnt/local_sdk" ]; then
                echo '{EVENT_PREFIX}{{"type":"status","content":"[DEV] Installing Local SDK..."}}'
                uv pip install -e /mnt/local_sdk
            fi
            """

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

        sdk_install_block = """
        if python -c "import charm" 2>/dev/null; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Pre-installed Charm SDK."}}'
        else
            echo '{EVENT_PREFIX}{{"type":"status","content":"SDK not found. Installing from PyPI..."}}'
            uv pip install --upgrade "charmos[runner]>=0.4.20"
        fi
        """

        artifact_upload_block = """
        if [ ! -z "$CHARM_ARTIFACT_UPLOAD_URL" ]; then
            echo '::CHARM_EVENT::{"type":"status","content":"Uploading Cloud Artifacts..."}'
            
            tar -czf output_artifacts.tar.gz \
                --exclude='./.*' \
                --exclude='__pycache__' \
                --exclude='charm.yaml' \
                --exclude='requirements.txt' \
                --exclude='pyproject.toml' \
                --exclude='*.py' \
                --exclude='output_artifacts.tar.gz' \
                --newer .charm_snapshot .

            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -T output_artifacts.tar.gz -H "Content-Type: application/gzip" "$CHARM_ARTIFACT_UPLOAD_URL")
            
            if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
                echo '::CHARM_EVENT::{"type":"status","content":"Artifacts Uploaded Successfully."}'
            else
                echo "::CHARM_EVENT::{\"type\":\"error\",\"content\":\"Artifact Upload Failed with code $HTTP_CODE\"}"
            fi
        fi
        """

        docker_copy_block = """
        if [ -z "$CHARM_ARTIFACT_UPLOAD_URL" ] && [ -d "/app/artifacts_mount" ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Syncing Artifacts to Host..."}}'
            find . -type f -newer .charm_snapshot \\
                -not -path "*/\\.*" \\
                -not -path "*/__pycache__/*" \\
                -not -name ".charm_snapshot" \\
                -not -name "charm.yaml" \\
                -not -name "*.py" \\
                -not -name ".env" \\
                > .charm_new_files

            while IFS= read -r file; do
                [ -f "$file" ] && cp --parents "$file" /app/artifacts_mount/ 2>/dev/null || true
            done < .charm_new_files
        fi
        """

        script = f"""
        set -e
        (while true; do echo '::CHARM_EVENT::{{"type":"thinking","content":"..."}}'; sleep 5; done) &
        HEARTBEAT_PID=$!
        trap "kill $HEARTBEAT_PID 2>/dev/null || true" EXIT

        mkdir -p agent_code && cd agent_code

        {source_setup_block}

        [ ! -f charm.yaml ] && echo '{EVENT_PREFIX}{{"type":"error","content":"Missing charm.yaml"}}' && exit 1

        echo "{b64_env_content}" | base64 -d > .env
        {dl_block}

        if [ -f "charm_memory.json" ]; then
            export CHARM_MEMORY_FILE="$(pwd)/charm_memory.json"
        else
            export CHARM_MEMORY_FILE="/app/artifacts_mount/charm_memory.json"
        fi
        mkdir -p /app/artifacts_mount

        {install_local_sdk_cmd}

        if [ -f pyproject.toml ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing dependencies..."}}'
            uv pip install -q -r pyproject.toml || uv pip install -q .
        elif [ -f requirements.txt ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing dependencies..."}}'
            uv pip install -q -r requirements.txt
        fi

        echo '{EVENT_PREFIX}{{"type":"status","content":"Configuring Runtime..."}}'
        
        {sdk_install_block}

        export PYTHONPATH=$PYTHONPATH:$(pwd)
        INPUT_JSON="$(echo {b64_payload} | base64 -d)"
        
        find . -type f > .charm_snapshot

        echo '{EVENT_PREFIX}{{"type":"status","content":"Running Agent..."}}'
        
        set +e
        export TERM=dumb 
        charm run . --json "$INPUT_JSON"
        EXIT_CODE=$?
        set -e

        if [ $EXIT_CODE -eq 0 ]; then
            {artifact_upload_block}
            {docker_copy_block}
        fi

        exit $EXIT_CODE
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
    ) -> AsyncGenerator[str, None]:
        run_timestamp = int(time.time())
        run_id = f"{agent_id}_{run_timestamp}"
        host_artifact_path = os.path.join(HOST_ARTIFACTS_ROOT, run_id)
        os.makedirs(host_artifact_path, exist_ok=True)

        if state_snapshot:
            input_payload["__charm_state__"] = state_snapshot

        if history:
            memory_file_name = "charm_memory.json"
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

        script_content = self._generate_bash_script(
            bundle_url=bundle_url,
            env_vars=env_vars,
            file_urls=file_urls,
            input_payload=input_payload,
            local_sdk_path=local_sdk_path,
            use_local_mount=should_mount_local,
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
        )

        try:
            async for log in self.backend.stream_logs(config):
                if "internal_run_finished" in log:
                    yield sse_pack("status", "Finalizing Output...")

                    if isinstance(self.backend, DockerBackend):
                        for root, _, files in os.walk(host_artifact_path):
                            for filename in files:
                                if filename in ["charm_memory.json", "runner_debug.log"]:
                                    continue
                                full_path = os.path.join(root, filename)
                                rel_path = os.path.relpath(full_path, host_artifact_path)
                                ct, _ = mimetypes.guess_type(full_path)
                                yield sse_pack(
                                    "internal_artifact_found",
                                    {
                                        "path": full_path,
                                        "rel_path": rel_path,
                                        "mime": ct,
                                        "run_id": run_id,
                                    },
                                )

                    elif artifact_upload_url:
                        final_tar_path = f"{agent_id}/{run_id}/output_artifacts.tar.gz"
                        public_url = supabase_client.storage.from_(
                            "agent_artifacts"
                        ).get_public_url(final_tar_path)
                        yield sse_pack(
                            "artifact",
                            {
                                "name": "All Output Files (Download)",
                                "url": public_url,
                                "mime": "application/gzip",
                            },
                        )

                yield log

        except Exception as e:
            logger.exception("Orchestrator Error")
            yield sse_pack("error", f"Orchestrator Error: {e}")
        finally:
            await self.backend.cleanup(run_id)
            shutil.rmtree(host_artifact_path, ignore_errors=True)
