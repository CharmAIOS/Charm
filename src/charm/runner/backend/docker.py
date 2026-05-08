import asyncio
import base64
import logging
import re
import time
import os
import tempfile
from collections import deque
from typing import AsyncGenerator, Dict

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None

from ...core.io import EVENT_PREFIX
from ...runner.protocol import sse_pack
from ...runner.utils import clean_log_fallback, is_duplicate_log
from .base import ExecutionBackend, RunConfig

logger = logging.getLogger("charm.runner.docker")

# Match Supabase storage signed URL so we can redact it whole (avoids replacing UUID inside URL with [CHARM_USER_ID_REDACTED] which would show a broken URL)
_SUPABASE_SIGNED_URL_RE = re.compile(
    r"https://[a-zA-Z0-9.-]+\.supabase\.co/storage/v1/object/sign/[^\s]+",
    re.ASCII,
)


class LogRedactor:
    def __init__(self, env_vars: Dict[str, str]):
        self.patterns = {}
        for k, v in env_vars.items():
            if v and len(str(v)) > 5:
                self.patterns[v] = f"[{k}_REDACTED]"

    def clean(self, text: str) -> str:
        if not text:
            return text
        # Redact entire bundle/signed URLs first so we never show a partially redacted URL (e.g. UUID replaced inside URL)
        text = _SUPABASE_SIGNED_URL_RE.sub("[CHARM_BUNDLE_URL_REDACTED]", text)
        for secret, replacement in self.patterns.items():
            if secret in text:
                text = text.replace(secret, replacement)
        return text


class DockerBackend(ExecutionBackend):
    def __init__(self):
        if not docker:
            raise RuntimeError("Docker SDK missing. Install 'pip install docker'.")
        try:
            self.client = docker.from_env()
        except DockerException:
            logger.error("Docker engine not accessible.")
            self.client = None

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        if not self.client:
            yield sse_pack("error", "Docker Engine Unavailable.")
            return

        start_time = time.time()
        redactor = LogRedactor(config.env_vars)
        recent_logs: deque[str] = deque(maxlen=50)
        sent_event_contents: deque[str] = deque(maxlen=20)

        HOST_NPM_CACHE = os.path.join(tempfile.gettempdir(), "charm_npm_cache")
        os.makedirs(HOST_NPM_CACHE, exist_ok=True)

        HOST_WORKSPACE = os.path.join(tempfile.gettempdir(), "charm_workspace")
        os.makedirs(HOST_WORKSPACE, exist_ok=True)

        # Cache
        volumes_config = {
            # Python Cache
            config.host_cache_dir: {"bind": "/root/.cache/uv", "mode": "rw"},
            # Node.js Cache
            HOST_NPM_CACHE: {"bind": "/root/.npm", "mode": "rw"},
            # Artifacts
            config.host_artifact_path: {"bind": "/app/artifacts_mount", "mode": "rw"},
            # Workspace
            HOST_WORKSPACE: {"bind": "/workspace", "mode": "rw"},
        }

        if config.local_source_path:
            volumes_config[config.local_source_path] = {
                "bind": "/app/local_source_mount",
                "mode": "ro",
            }

        # Mount local SDK for dev installs (LOCAL_SDK_HOST_PATH)
        if config.local_sdk_path and os.path.isdir(config.local_sdk_path):
            volumes_config[config.local_sdk_path] = {
                "bind": "/mnt/local_sdk",
                "mode": "ro",
            }

        if config.bundle_local_path:
            _mount_dir = os.path.dirname(config.bundle_local_path)
            volumes_config[_mount_dir] = {"bind": "/app/bundle_mount", "mode": "ro"}

        b64_script = base64.b64encode(config.script_content.encode("utf-8")).decode("utf-8")
        full_command = f'/bin/bash -c "echo {b64_script} | base64 -d | bash"'

        container = None
        exit_code = -1

        try:
            # Use dynamic image from config, fallback to default
            IMAGE_NAME = config.image or "ucmind/runner-base:latest"

            logger.info(f"Spawning container with image: {IMAGE_NAME}")

            container = self.client.containers.run(
                IMAGE_NAME,
                command=full_command,
                environment={**config.env_vars, "PYTHONUNBUFFERED": "1"},
                detach=True,
                mem_limit="2048m",
                nano_cpus=1000000000,
                network_mode="bridge",
                extra_hosts={"host.docker.internal": "host-gateway"},
                working_dir="/app",
                volumes=volumes_config,
                # cap_drop=["ALL"],
                # security_opt=["no-new-privileges"],
            )

            logs_iterator = container.logs(stream=True, follow=True, stdout=True, stderr=True)

            buffer = ""

            for chunk in logs_iterator:
                decoded_chunk = chunk.decode("utf-8", errors="replace")
                buffer += decoded_chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    clean_line = line.strip()
                    safe_line = redactor.clean(clean_line)

                    if not safe_line:
                        continue

                    # Parse both __CHARM_EVENT__ and ::CHARM_EVENT:: (script uses both)
                    json_part = None
                    if EVENT_PREFIX in safe_line:
                        try:
                            json_part = safe_line.split(EVENT_PREFIX)[1].strip()
                        except IndexError:
                            pass
                    elif "::CHARM_EVENT::" in safe_line:
                        try:
                            json_part = safe_line.split("::CHARM_EVENT::", 1)[1].strip()
                        except IndexError:
                            pass
                    if json_part:
                        try:
                            import json
                            payload = json.loads(json_part)
                            content_str = str(payload.get("content", ""))
                            if content_str and payload.get("type") != "thinking":
                                sent_event_contents.append(content_str)
                            yield f"data: {json_part}\n\n"
                        except Exception:
                            pass
                        continue

                    if is_duplicate_log(safe_line, sent_event_contents):
                        continue

                    processed = clean_log_fallback(safe_line)
                    if processed:
                        yield sse_pack("thinking", processed + "\n")
                        recent_logs.append(processed)

                await asyncio.sleep(0)

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, container.wait)
            exit_code = result.get("StatusCode", 1)

            if exit_code != 0:
                # Drop raw protocol lines from error detail so UI stays readable
                err_lines = [
                    line for line in recent_logs
                    if EVENT_PREFIX not in line and "::CHARM_EVENT::" not in line
                ]
                err_detail = "\n".join(err_lines) if err_lines else "See runner logs."
                yield sse_pack("error", f"Execution Failed (Code {exit_code}).\n{err_detail}")

        except Exception as e:
            yield sse_pack("error", f"Docker Execution Error: {str(e)}")

        finally:
            if container:
                try:
                    container.remove(force=True)
                except:
                    pass

            yield sse_pack(
                "internal_run_finished",
                {"exit_code": exit_code, "duration_ms": int((time.time() - start_time) * 1000)},
            )

    async def cleanup(self, run_id: str):
        pass
