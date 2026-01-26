import asyncio
import base64
import logging
import time
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


class LogRedactor:
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

        redactor = LogRedactor(config.env_vars)
        recent_logs: deque[str] = deque(maxlen=50)
        sent_event_contents: deque[str] = deque(maxlen=20)
        volumes_config = {
            config.host_cache_dir: {"bind": "/root/.cache/uv", "mode": "rw"},
            config.host_artifact_path: {"bind": "/app/artifacts_mount", "mode": "rw"},
        }

        if config.local_source_path:
            volumes_config[config.local_source_path] = {
                "bind": "/app/local_source_mount",
                "mode": "ro",
            }

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

            start_time = time.time()
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

                    if EVENT_PREFIX in safe_line:
                        try:
                            json_part = safe_line.split(EVENT_PREFIX)[1]
                            import json

                            payload = json.loads(json_part)
                            content_str = str(payload.get("content", ""))
                            if content_str:
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
                err_detail = "\n".join(recent_logs)
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
