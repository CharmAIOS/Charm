import asyncio
import base64
import functools
import hashlib
import logging
import os
import random
import time
from typing import AsyncGenerator, Dict

try:
    from google.cloud import run_v2
    from google.cloud import logging as cloud_logging
    from google.api_core import exceptions as google_exceptions
except ImportError:
    run_v2 = None
    cloud_logging = None

from ...core.io import EVENT_PREFIX
from ...runner.protocol import sse_pack
from ...runner.utils import clean_log_fallback
from .base import ExecutionBackend, RunConfig

logger = logging.getLogger("charm.runner.cloud_run")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r. Falling back to %s.", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r. Falling back to %s.", name, raw, default)
        return default


class CloudRunBackend(ExecutionBackend):

    _job_cache: Dict[str, str] = {}

    def __init__(self):
        if not run_v2 or not cloud_logging:
            raise RuntimeError(
                "Google Cloud SDK missing. Install 'google-cloud-run' and 'google-cloud-logging'."
            )

        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.region = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

        if not self.project_id:
            raise ValueError("Missing GOOGLE_CLOUD_PROJECT environment variable.")

        self.jobs_client = run_v2.JobsAsyncClient()
        self.logging_client = cloud_logging.Client(project=self.project_id)
        self.parent = f"projects/{self.project_id}/locations/{self.region}"
        self.storage_bucket = os.getenv("CHARM_USER_BUCKET_NAME")
        self.log_poll_base_seconds = max(
            1.0, _env_float("CHARM_LOG_POLL_INTERVAL_SECONDS", 2.0)
        )
        self.log_poll_max_seconds = max(
            self.log_poll_base_seconds,
            _env_float("CHARM_LOG_POLL_MAX_INTERVAL_SECONDS", 15.0),
        )
        self.trailing_attempts = max(1, _env_int("CHARM_LOG_TRAILING_ATTEMPTS", 6))
        self.log_read_concurrency = max(1, _env_int("CHARM_LOG_READ_CONCURRENCY", 2))
        self.default_serverless_timeout_seconds = max(
            1, _env_int("CHARM_DEFAULT_SERVERLESS_TIMEOUT_SECONDS", 600)
        )
        self.min_serverless_timeout_seconds = max(
            1, _env_int("CHARM_MIN_SERVERLESS_TIMEOUT_SECONDS", 30)
        )
        self.max_serverless_timeout_seconds = max(
            self.min_serverless_timeout_seconds,
            _env_int("CHARM_MAX_SERVERLESS_TIMEOUT_SECONDS", 1800),
        )
        self.raw_log_echo = os.getenv("CHARM_CLOUD_RUN_RAW_LOG_ECHO", "").lower() in (
            "1",
            "true",
            "yes",
        )
        self._log_read_semaphore = asyncio.Semaphore(self.log_read_concurrency)

    def _resolve_timeout_seconds(self, config: RunConfig) -> int:
        declared = (
            config.timeout_seconds
            if config.timeout_seconds is not None
            else self.default_serverless_timeout_seconds
        )
        timeout = max(
            self.min_serverless_timeout_seconds,
            min(self.max_serverless_timeout_seconds, int(declared)),
        )

        if timeout != int(declared):
            logger.warning(
                "[CloudRun] Timeout clamped from %ss to %ss (allowed %ss-%ss)",
                declared,
                timeout,
                self.min_serverless_timeout_seconds,
                self.max_serverless_timeout_seconds,
            )
        return timeout

    def _make_job_id(self, agent_id: str, spec_hash: str) -> str:
        safe = agent_id.replace("_", "-").lower()[:32]
        return f"charm-{safe}-{spec_hash[:8]}"

    async def _get_or_create_job(self, config: RunConfig) -> str:
        default_fallback = (
            "us-central1-docker.pkg.dev/charm-cloud-runner/charm/runner-standard:latest"
        )
        worker_image = config.image or os.getenv("CHARM_WORKER_IMAGE", default_fallback)
        timeout_seconds = self._resolve_timeout_seconds(config)
        # Include key env vars in hash so different configs create different jobs
        env_hash = ""
        if config.env_vars:
            bundle_path = config.env_vars.get("CHARM_BUNDLE_GCS_PATH", "")
            if bundle_path:
                env_hash = hashlib.sha1(bundle_path.encode("utf-8")).hexdigest()[:8]
        spec_hash = hashlib.sha1(
            f"{worker_image}|{timeout_seconds}|{env_hash}".encode("utf-8")
        ).hexdigest()
        job_id = self._make_job_id(config.agent_id, spec_hash)
        job_fqn = f"{self.parent}/jobs/{job_id}"

        if job_fqn in self._job_cache:
            logger.info(f"[CloudRun] Reusing cached job: {job_id}")
            return self._job_cache[job_fqn]

        try:
            request = run_v2.GetJobRequest(name=job_fqn)
            existing = await self.jobs_client.get_job(request=request)
            logger.info(f"[CloudRun] Found existing job: {job_id}")
            # Check if job needs update (env vars may have changed)
            if config.env_vars:
                needs_update = True
                # Check if this job has the expected env vars
                container_spec = existing.template.template.containers[0]
                existing_env_names = {e["name"] for e in container_spec.env}
                for key in config.env_vars:
                    if key not in existing_env_names:
                        needs_update = True
                        break
                if needs_update:
                    logger.info(f"[CloudRun] Job needs update, deleting and recreating...")
                    delete_req = run_v2.DeleteJobRequest(name=job_fqn)
                    await self.jobs_client.delete_job(request=delete_req)
                    # Clear from cache to force recreation
                    if job_fqn in self._job_cache:
                        del self._job_cache[job_fqn]
                        raise google_exceptions.NotFound("Job deleted, will recreate")
            self._job_cache[job_fqn] = existing.name
            return existing.name
        except google_exceptions.NotFound:
            logger.info(f"[CloudRun] Job {job_id} not found, creating...")

        logger.info(
            "[CloudRun] Target Image: %s | Timeout: %ss | JobId: %s",
            worker_image,
            timeout_seconds,
            job_id,
        )

        container = {
            "image": worker_image,
            "command": ["/bin/bash", "-c"],
            "args": ["echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash"],
            "env": [
                {"name": "PYTHONUNBUFFERED", "value": "1"},
                {"name": "CHARM_BOOTSTRAP_SCRIPT", "value": "ZWNobyAncmVhZHkn"},
            ],
            "resources": {
                "limits": {
                    "memory": "2Gi",
                    "cpu": "2000m",
                }
            },
        }

        # Pass env vars from config (includes bundle path, etc.)
        if config.env_vars:
            for key, value in config.env_vars.items():
                container["env"].append({"name": key, "value": value})

        job = run_v2.Job()
        job.template.template.max_retries = 0
        job.template.template.timeout = f"{timeout_seconds}s"

        if self.storage_bucket:
            container["volume_mounts"] = [{"name": "gcs-persistence", "mount_path": "/workspace"}]
            job.template.template.volumes = [
                {
                    "name": "gcs-persistence",
                    "gcs": {"bucket": self.storage_bucket, "read_only": False},
                }
            ]

        job.template.template.containers = [container]

        request = run_v2.CreateJobRequest(parent=self.parent, job=job, job_id=job_id)
        logger.info(f"[CloudRun] Creating Job {job_id} using image {worker_image}...")
        try:
            operation = await self.jobs_client.create_job(request=request)
            result = await operation.result()
            self._job_cache[job_fqn] = result.name
            return result.name
        except google_exceptions.AlreadyExists:
            # Race condition: two concurrent requests tried to create the same job
            # simultaneously (e.g. auto-upgrade firing for multiple users of one agent).
            # The job was created by the other request — just fetch and use it.
            logger.info(f"[CloudRun] Job {job_id} already exists (race), fetching existing...")
            existing = await self.jobs_client.get_job(run_v2.GetJobRequest(name=job_fqn))
            self._job_cache[job_fqn] = existing.name
            return existing.name

    async def _fetch_logs_sync(self, filter_str):
        entries = self.logging_client.list_entries(
            filter_=filter_str,
            order_by=cloud_logging.DESCENDING,
            page_size=50,
        )
        return sorted(list(entries), key=lambda x: x.timestamp)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        text = str(exc).upper()
        return "RATE_LIMIT_EXCEEDED" in text or " 429 " in text or "429" in text

    async def _list_entries(
        self, loop: asyncio.AbstractEventLoop, filter_str: str, page_size: int
    ):
        async with self._log_read_semaphore:
            entries = await loop.run_in_executor(
                None,
                functools.partial(
                    self.logging_client.list_entries,
                    filter_=filter_str,
                    order_by=cloud_logging.DESCENDING,
                    page_size=page_size,
                ),
            )
        return sorted(list(entries), key=lambda x: x.timestamp)

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        job_name = ""
        start_time = time.monotonic()

        try:
            yield sse_pack("status", "Provisioning Cloud Sandbox...")
            job_name = await self._get_or_create_job(config)

            b64_script = base64.b64encode(config.script_content.encode("utf-8")).decode("utf-8")
            env_overrides = [
                run_v2.EnvVar(name="PYTHONUNBUFFERED", value="1"),
                run_v2.EnvVar(name="CHARM_BOOTSTRAP_SCRIPT", value=b64_script),
                *[
                    run_v2.EnvVar(name=k, value=str(v))
                    for k, v in config.env_vars.items()
                    if v is not None
                ],
            ]

            yield sse_pack("status", "Starting Execution Environment...")
            run_request = run_v2.RunJobRequest(
                name=job_name,
                overrides=run_v2.RunJobRequest.Overrides(
                    container_overrides=[
                        run_v2.RunJobRequest.Overrides.ContainerOverride(
                            env=env_overrides,
                        )
                    ],
                ),
            )
            operation = await self.jobs_client.run_job(request=run_request)

            execution_name = operation.metadata.name
            execution_id = execution_name.split("/")[-1]
            logger.info(f"[CloudRun] Tailing logs for execution: {execution_name}")

            filter_str = f"""
            resource.type="cloud_run_job"
            labels."run.googleapis.com/execution_name"="{execution_id}"
            """

            is_done = False
            sent_event_ids = set()
            loop = asyncio.get_running_loop()
            poll_sleep_seconds = self.log_poll_base_seconds

            while not is_done:
                if await operation.done():
                    is_done = True

                sleep_seconds = poll_sleep_seconds
                try:
                    new_logs = await self._list_entries(
                        loop=loop,
                        filter_str=filter_str,
                        page_size=200,
                    )
                    poll_sleep_seconds = self.log_poll_base_seconds
                except Exception as e:
                    if self._is_rate_limited(e):
                        poll_sleep_seconds = min(
                            self.log_poll_max_seconds,
                            max(self.log_poll_base_seconds, poll_sleep_seconds * 2),
                        )
                        sleep_seconds = poll_sleep_seconds + random.uniform(0.0, 0.75)
                        logger.warning(
                            "Log fetch rate-limited (429). Backing off %.2fs: %s",
                            sleep_seconds,
                            e,
                        )
                    else:
                        logger.warning("Log fetch failed (transient): %s", e)
                    new_logs = []

                for entry in new_logs:
                    if entry.insert_id in sent_event_ids:
                        continue

                    sent_event_ids.add(entry.insert_id)
                    payload = entry.payload

                    if self.raw_log_echo:
                        print(f"[RAW LOG] {payload}")

                    if isinstance(payload, str):
                        line = payload.strip()
                        if EVENT_PREFIX in line:
                            try:
                                json_part = line.split(EVENT_PREFIX)[1].strip()
                                yield f"data: {json_part}\n\n"
                            except Exception:
                                pass
                        elif "::CHARM_EVENT::" in line:
                            try:
                                json_part = line.split("::CHARM_EVENT::")[1].strip()
                                yield f"data: {json_part}\n\n"
                            except Exception:
                                pass
                        else:
                            clean = clean_log_fallback(line)
                            if clean:
                                yield sse_pack("thinking", clean + "\n")
                            else:
                                if "Memory" in line or "Exited" in line or "Error" in line:
                                    yield sse_pack("error", f"System: {line}\n")

                if not is_done:
                    await asyncio.sleep(sleep_seconds)

            found_final = False
            max_trailing_attempts = self.trailing_attempts
            for attempt in range(max_trailing_attempts):
                await asyncio.sleep(2)
                try:
                    tail_logs = await self._list_entries(
                        loop=loop,
                        filter_str=filter_str,
                        page_size=200,
                    )
                    for entry in tail_logs:
                        if entry.insert_id in sent_event_ids:
                            continue
                        sent_event_ids.add(entry.insert_id)
                        payload = entry.payload
                        if isinstance(payload, str):
                            line = payload.strip()
                            if EVENT_PREFIX in line:
                                try:
                                    json_part = line.split(EVENT_PREFIX)[1].strip()
                                    yield f"data: {json_part}\n\n"
                                    if '"type": "final"' in json_part or '"type":"final"' in json_part:
                                        found_final = True
                                    if '"type": "error"' in json_part or '"type":"error"' in json_part:
                                        found_final = True
                                except Exception:
                                    pass
                            elif "::CHARM_EVENT::" in line:
                                try:
                                    json_part = line.split("::CHARM_EVENT::")[1].strip()
                                    yield f"data: {json_part}\n\n"
                                except Exception:
                                    pass
                except Exception as e:
                    if self._is_rate_limited(e):
                        logger.debug("Trailing log fetch rate-limited: %s", e)
                    else:
                        logger.debug("Trailing log fetch failed: %s", e)

                if found_final:
                    logger.info("[CloudRun] Found final/error event on trailing attempt %d", attempt + 1)
                    break

            try:
                await operation.result()
                duration_ms = int((time.monotonic() - start_time) * 1000)
                yield sse_pack("status", "Cloud Job Completed Successfully.")
                yield sse_pack(
                    "internal_run_finished", {"exit_code": 0, "duration_ms": duration_ms}
                )
            except Exception as job_error:
                tail_lines = []
                try:
                    final_logs = await self._list_entries(
                        loop=loop,
                        filter_str=filter_str,
                        page_size=100,
                    )
                    for entry in sorted(final_logs, key=lambda x: x.timestamp)[-15:]:
                        if isinstance(entry.payload, str) and entry.payload.strip():
                            tail_lines.append(entry.payload.strip())
                except Exception as log_err:
                    logger.warning(f"Failed to fetch job log tail: {log_err}")
                tail = "\n".join(tail_lines) if tail_lines else ""
                err_msg = str(job_error)
                if tail:
                    err_msg = f"{err_msg}\n\nLast log lines from job:\n{tail}"
                yield sse_pack("error", err_msg)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                yield sse_pack(
                    "internal_run_finished", {"exit_code": 1, "duration_ms": duration_ms}
                )

        except Exception as e:
            logger.exception("Cloud Run Error")
            yield sse_pack("error", f"Cloud Infrastructure Error: {str(e)}")

        finally:
            if job_name:
                force_delete = os.environ.get("CHARM_DELETE_JOB_AFTER_RUN", "").lower() in ("1", "true", "yes")
                if force_delete:
                    yield sse_pack("status", "Cleaning up resources...")
                    await self.cleanup(job_name)
                else:
                    logger.info(f"[CloudRun] Keeping job for reuse: {job_name}")

    async def cleanup(self, job_name_or_run_id: str):
        if "/jobs/" not in job_name_or_run_id:
            logger.debug(f"[CloudRun] cleanup called with run_id {job_name_or_run_id}, skipping (job reuse)")
            return

        try:
            request = run_v2.DeleteJobRequest(name=job_name_or_run_id)
            await self.jobs_client.delete_job(request=request)
            self._job_cache.pop(job_name_or_run_id, None)
            logger.info(f"[CloudRun] Deleted job {job_name_or_run_id}")
        except Exception as e:
            logger.warning(f"[CloudRun] Failed to delete job {job_name_or_run_id}: {e}")
