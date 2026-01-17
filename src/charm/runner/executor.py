import asyncio
import base64
import json
import logging
import mimetypes
import os
import shlex
import shutil
import tempfile
import time
from collections import deque
from typing import Any, AsyncGenerator, Dict, List, Optional

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None

from .protocol import EVENT_PREFIX, sse_pack
from .utils import clean_log_fallback, is_duplicate_log

# Configuration Constants
TEMP_DIR = tempfile.gettempdir()
HOST_CACHE_DIR = os.path.join(TEMP_DIR, "charm_uv_cache")
HOST_ARTIFACTS_ROOT = os.path.join(TEMP_DIR, "charm_artifacts_buffer")
LIMIT_TIMEOUT = 600
LIMIT_CPU = 1000000000
LIMIT_MEM = "2048m"

logger = logging.getLogger("charm.runner")


class LogRedactor:
    """
    Responsible for replacing sensitive environment variables in logs with [KEY_NAME_REDACTED].
    """

    def __init__(self, env_vars: Dict[str, str]):
        self.patterns = {}
        for k, v in env_vars.items():
            if v and len(str(v)) > 5:
                self.patterns[v] = f"[{k}_REDACTED]"

    def clean(self, text: str) -> str:
        if not text:
            return text
        for secret, replacement in self.patterns.items():
            if secret in text:
                text = text.replace(secret, replacement)
        return text


class CharmDockerExecutor:
    """
    Manages the execution of Charm Agents within isolated Docker containers.
    Handles script generation, container lifecycle, log streaming, and artifact retrieval.
    """

    def __init__(self):
        if not docker:
            raise RuntimeError("Docker SDK not installed. Install via 'pip install docker'.")

        try:
            self.client = docker.from_env()
        except DockerException:
            logger.error("Docker engine is not running or accessible.")
            self.client = None

        # Ensure host directories exist
        os.makedirs(HOST_CACHE_DIR, exist_ok=True)
        os.makedirs(HOST_ARTIFACTS_ROOT, exist_ok=True)

    def _generate_bash_script(
        self,
        bundle_url: str,
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        input_payload: Dict[str, Any],
        local_sdk_path: Optional[str] = None,
        use_local_mount: bool = False,  # Toggle for local simulation
    ) -> str:
        """Generates the bash script that runs inside the container."""

        # Prepare Environment Variables (.env)
        env_file_lines = []
        for k, v in env_vars.items():
            safe_val = str(v).replace("\n", "\\n").replace('"', '\\"')
            env_file_lines.append(f'{k}="{safe_val}"')
        env_file_content = "\n".join(env_file_lines)
        b64_env_content = base64.b64encode(env_file_content.encode()).decode()

        # Prepare File Injections (curl)
        dl_cmds = []
        if file_urls:
            for f, u in file_urls.items():
                dl_cmds.append(f"curl -s -L {shlex.quote(u)} -o {shlex.quote(os.path.basename(f))}")
        dl_block = "\n".join(dl_cmds) if dl_cmds else "true"

        # Encode Input Payload
        input_json_str = json.dumps(input_payload)
        b64_payload = base64.b64encode(input_json_str.encode()).decode()

        # Optional: Install local SDK (Dev Mode)
        install_local_sdk_cmd = ""
        if local_sdk_path:
            install_local_sdk_cmd = f"""
            if [ -d "/mnt/local_sdk" ]; then
                echo '{EVENT_PREFIX}{{"type":"status","content":"[DEV] Installing Local SDK from Host..."}}'
                uv pip install -e /mnt/local_sdk
            fi
            """

        # Source Code Strategy
        if use_local_mount:
            # Mode A: Local Simulation (Copy from read-only mount)
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Local Source Code (Sandbox Mode)..."}}'
            
            # Check mount point
            if [ ! -d "/app/local_source_mount" ]; then
                echo '{EVENT_PREFIX}{{"type":"error","content":"Local mount point not found."}}'
                exit 1
            fi

            # Copy files to working directory (ignoring hidden git/env files if needed, but cp -r covers most)
            # We use cp -rT to merge contents into current dir
            cp -r /app/local_source_mount/. .
            """
        else:
            # Mode B: Cloud Production (Download Bundle)
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Downloading Bundle..."}}'
            curl -s -L {shlex.quote(bundle_url)} -o bundle.tar.gz
            
            echo '{EVENT_PREFIX}{{"type":"status","content":"Extracting..."}}'
            tar -xzf bundle.tar.gz --no-same-owner
            rm bundle.tar.gz
            """

        # 6. Construct Final Script
        script = f"""
        set -e
        
        # Heartbeat to keep Caddy alive
        (while true; do echo '::CHARM_EVENT::{{"type":"thinking","content":"..."}}'; sleep 2; done) &
        HEARTBEAT_PID=$!
        trap "kill $HEARTBEAT_PID 2>/dev/null || true" EXIT

        mkdir -p agent_code
        cd agent_code

        {source_setup_block}

        if [ ! -f charm.yaml ]; then
            echo '{EVENT_PREFIX}{{"type":"error","content":"Missing charm.yaml"}}'
            exit 1
        fi

        echo "{b64_env_content}" | base64 -d > .env
        echo '{EVENT_PREFIX}{{"type":"status","content":"Environment Configured."}}'

        {dl_block}

        mkdir -p artifacts
        export CHARM_MEMORY_FILE="/app/artifacts_mount/charm_memory.json"

        {install_local_sdk_cmd}

        if [ -f pyproject.toml ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing dependencies..."}}'
            uv pip install -q -r pyproject.toml || uv pip install -q .
        elif [ -f requirements.txt ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing dependencies..."}}'
            uv pip install -q -r requirements.txt
        fi

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
            echo '{EVENT_PREFIX}{{"type":"status","content":"Harvesting Results..."}}'
            # Find new files to copy to artifacts mount
            find . -type f -newer .charm_snapshot \\
                -not -path "*/\\.*" \\
                -not -path "*/__pycache__/*" \\
                -not -name ".charm_snapshot" \\
                -not -name "charm.yaml" \\
                -not -name "requirements.txt" \\
                -not -name "pyproject.toml" \\
                -not -name "*.py" \\
                -not -name "*.js" \\
                -not -name "*.ts" \\
                -not -name ".env" \\
                > .charm_new_files

            while IFS= read -r file; do
                if [ -f "$file" ]; then
                    cp --parents "$file" /app/artifacts_mount/ 2>/dev/null || true
                fi
            done < .charm_new_files
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
    ) -> AsyncGenerator[str, None]:
        """
        Orchestrates the Docker execution flow.
        Yields SSE-formatted strings.

        Args:
            local_source_path: If provided, mounts this host path instead of downloading bundle_url.
        """
        if not self.client:
            yield sse_pack("error", "Docker Engine Unavailable.")
            return

        # Prepare Run ID and paths
        run_timestamp = int(time.time())
        run_id = f"{agent_id}_{run_timestamp}"
        host_artifact_path = os.path.join(HOST_ARTIFACTS_ROOT, run_id)
        os.makedirs(host_artifact_path, exist_ok=True)

        # Inject State & History
        if state_snapshot:
            input_payload["__charm_state__"] = state_snapshot

        if history:
            try:
                memory_path = os.path.join(host_artifact_path, "charm_memory.json")
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False)
                yield sse_pack("status", f"Injecting {len(history)} messages of history...")
            except Exception as e:
                logger.warning(f"Failed to write memory: {e}")

        # Check for Local SDK Mount (for dev/test)
        local_sdk_path = os.getenv("LOCAL_SDK_HOST_PATH")

        # Determine Source Code Strategy
        use_local_mount = bool(local_source_path)

        # Initialize Redactor for this run
        redactor = LogRedactor(env_vars)

        # Generate Execution Script (Dynamic based on mode)
        script_content = self._generate_bash_script(
            bundle_url=bundle_url,
            env_vars=env_vars,
            file_urls=file_urls,
            input_payload=input_payload,
            local_sdk_path=local_sdk_path,
            use_local_mount=use_local_mount,
        )
        b64_script = base64.b64encode(script_content.encode("utf-8")).decode("utf-8")
        full_command = f'/bin/bash -c "echo {b64_script} | base64 -d | bash"'

        container = None
        exit_code = -1
        start_time = time.time()

        try:
            # Mount Configuration
            volumes_config = {
                HOST_CACHE_DIR: {"bind": "/root/.cache/uv", "mode": "rw"},
                host_artifact_path: {"bind": "/app/artifacts_mount", "mode": "rw"},
            }
            if local_sdk_path:
                volumes_config[local_sdk_path] = {"bind": "/mnt/local_sdk", "mode": "rw"}

            # Mount user's code if in local mode
            if use_local_mount and local_source_path:
                volumes_config[local_source_path] = {
                    "bind": "/app/local_source_mount",
                    "mode": "ro",
                }

            # Start Container
            IMAGE_NAME = "ucmind/runner-base:latest"

            logger.info(f"Checking for Runner Image: {IMAGE_NAME}...")

            try:
                self.client.images.get(IMAGE_NAME)
                logger.info(f"Image {IMAGE_NAME} found locally. Skipping pull.")

            except docker.errors.ImageNotFound:
                logger.info(f"Image not found locally. Pulling {IMAGE_NAME}...")
                try:
                    self.client.images.pull(IMAGE_NAME)
                except Exception as e:
                    logger.warning(f"Failed to pull image: {e}")
            except Exception as e:
                logger.warning(f"Error checking image status: {e}")

            # Start Container
            container = self.client.containers.run(
                IMAGE_NAME,
                command=full_command,
                environment={**env_vars, "PYTHONUNBUFFERED": "1"},
                detach=True,
                mem_limit=LIMIT_MEM,
                memswap_limit=LIMIT_MEM,
                nano_cpus=LIMIT_CPU,
                pids_limit=100,
                network_mode="bridge",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                working_dir="/app",
                tty=False,
                tmpfs={"/tmp": ""},
                volumes=volumes_config,
            )

            # Log Streaming State
            recent_logs: deque[str] = deque(maxlen=50)
            sent_event_contents: deque[str] = deque(maxlen=20)
            debug_log_path = os.path.join(host_artifact_path, "runner_debug.log")

            # --- Internal Helper: Log Reader ---
            async def read_logs_task():
                with open(debug_log_path, "w", encoding="utf-8") as debug_file:
                    logs_iterator = container.logs(
                        stream=True, follow=True, stdout=True, stderr=True
                    )
                    buffer = ""

                    for chunk in logs_iterator:
                        current_task = asyncio.current_task()
                        if current_task and current_task.cancelled():
                            break

                        decoded_chunk = chunk.decode("utf-8", errors="replace")
                        buffer += decoded_chunk

                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)

                            clean_line = line.strip()
                            safe_line = redactor.clean(clean_line)

                            debug_file.write(safe_line + "\n")

                            if not safe_line:
                                continue

                            # 1. Handle Structured Events from SDK
                            if EVENT_PREFIX in safe_line:
                                try:
                                    json_part = safe_line.split(EVENT_PREFIX)[1]
                                    payload = json.loads(json_part)
                                    content_str = str(payload.get("content", ""))
                                    if content_str:
                                        sent_event_contents.append(content_str)
                                    yield f"data: {json_part}\n\n"
                                except json.JSONDecodeError:
                                    pass
                                except Exception:
                                    pass
                                continue

                            # 2. Filter Duplicates & Noise (Using safe_line)
                            if is_duplicate_log(safe_line, sent_event_contents):
                                continue
                            if "asyncio.get_event_loop" in safe_line:
                                continue

                            # 3. Emit Standard Logs as 'thinking' (Using safe_line)
                            processed = clean_log_fallback(safe_line)
                            if processed:
                                yield sse_pack("thinking", processed + "\n")
                                recent_logs.append(processed)

                            await asyncio.sleep(0)

                    # Flush buffer
                    if buffer.strip():
                        safe_buffer = redactor.clean(buffer.strip())
                        debug_file.write(safe_buffer + "\n")
                        processed = clean_log_fallback(safe_buffer)
                        if processed:
                            yield sse_pack("thinking", processed + "\n")

            # --- Internal Helper: Wait for Container ---
            async def wait_container_task():
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, container.wait)

            wait_future = asyncio.create_task(wait_container_task())

            try:
                # Stream logs until container exits or timeout
                async for sse_msg in read_logs_task():
                    yield sse_msg
                    if wait_future.done():
                        break
                    if time.time() - start_time > LIMIT_TIMEOUT:
                        raise asyncio.TimeoutError()

                result = await asyncio.wait_for(wait_future, timeout=5)
                exit_code = result.get("StatusCode", 1)

            except asyncio.TimeoutError:
                yield sse_pack("error", "Execution Timeout.")
                exit_code = 124
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                wait_future.cancel()

            # Handle Artifacts & Final Status
            if exit_code == 0:
                yield sse_pack("status", "Processing Artifacts...")

                # Scan artifacts and yield a special internal event for the Platform to handle
                for root, _, files in os.walk(host_artifact_path):
                    for filename in files:
                        if filename == "runner_debug.log":
                            continue
                        if filename == "charm_memory.json":
                            continue

                        file_full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(file_full_path, host_artifact_path)

                        if os.path.isfile(file_full_path):
                            ct, _ = mimetypes.guess_type(file_full_path)

                            yield sse_pack(
                                "internal_artifact_found",
                                {
                                    "path": file_full_path,
                                    "rel_path": rel_path,
                                    "mime": ct,
                                    "run_id": run_id,
                                },
                            )
            else:
                err_detail = "\n".join(recent_logs)
                yield sse_pack("error", f"Agent Failed (Code {exit_code}).\n\nLogs:\n{err_detail}")

        except Exception as e:
            yield sse_pack("error", f"System Error: {str(e)}")

        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

            # Clean up temp files
            shutil.rmtree(host_artifact_path, ignore_errors=True)

            yield sse_pack(
                "internal_run_finished",
                {"exit_code": exit_code, "duration_ms": int((time.time() - start_time) * 1000)},
            )
