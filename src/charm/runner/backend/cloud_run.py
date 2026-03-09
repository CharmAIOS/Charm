import asyncio
import logging
import os
import json
import time
import base64
import uuid
import functools
from typing import AsyncGenerator, Dict, Any

try:
    from google.cloud import run_v2
    from google.cloud import logging as cloud_logging
    from google.api_core import exceptions as google_exceptions
except ImportError:
    run_v2 = None
    cloud_logging = None

from ...core.io import EVENT_PREFIX
from ...runner.protocol import sse_pack
from ...runner.utils import clean_log_fallback, is_duplicate_log
from .base import ExecutionBackend, RunConfig

logger = logging.getLogger("charm.runner.cloud_run")


class CloudRunBackend(ExecutionBackend):
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

    async def _create_job(self, job_id: str, config: RunConfig) -> str:
        b64_script = base64.b64encode(config.script_content.encode("utf-8")).decode("utf-8")

        env_vars = [
            {"name": "PYTHONUNBUFFERED", "value": "1"},
            {"name": "CHARM_BOOTSTRAP_SCRIPT", "value": b64_script},
            *[{"name": k, "value": str(v)} for k, v in config.env_vars.items() if v is not None],
        ]

        default_fallback = (
            "us-central1-docker.pkg.dev/charm-cloud-runner/charm/runner-standard:latest"
        )
        worker_image = config.image or os.getenv("CHARM_WORKER_IMAGE", default_fallback)

        logger.info(f"[CloudRun] Target Image resolved to: {worker_image}")

        logger.info(f"[CloudRun] Creating Serverless Task Job {job_id}")

        container = {
            "image": worker_image,
            "command": ["/bin/bash", "-c"],
            "args": ["echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash"],
            "env": env_vars,
            "resources": {
                "limits": {
                    "memory": "1Gi",
                    "cpu": "1000m",
                }
            },
        }

        job = run_v2.Job()
        job.template.template.max_retries = 0

        # Serverless hard limit: 10 minutes (regardless of adapter type)
        job.template.template.timeout = "600s"

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

        operation = await self.jobs_client.create_job(request=request)
        logger.info(f"[CloudRun] Creating Job {job_id} using image {worker_image}...")
        result = await operation.result()
        return result.name

    async def _fetch_logs_sync(self, filter_str):
        entries = self.logging_client.list_entries(
            filter_=filter_str,
            order_by=cloud_logging.DESCENDING,
            page_size=50,
        )
        return sorted(list(entries), key=lambda x: x.timestamp)

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        safe_agent_id = config.agent_id.replace("_", "-").lower()[:20]
        job_id = f"charm-{safe_agent_id}-{uuid.uuid4().hex[:6]}"
        job_name = ""

        try:
            yield sse_pack("status", "Provisioning Cloud Sandbox...")
            job_name = await self._create_job(job_id, config)

            yield sse_pack("status", "Starting Execution Environment...")
            run_request = run_v2.RunJobRequest(name=job_name)
            operation = await self.jobs_client.run_job(request=run_request)

            execution_name = operation.metadata.name
            execution_id = execution_name.split("/")[-1]  # e.g. charm-2247afda-4665-4a01-b-0cba9b-cg7nt
            logger.info(f"[CloudRun] Tailing logs for execution: {execution_name}")

            # Fetch logs from the Job *container* (script stdout/stderr), not the Runner API.
            # In GCP: Cloud Run > Jobs > <job> > Executions > <execution> > LOGS, or
            # Logs Explorer: resource.type="cloud_run_job" + label run.googleapis.com/execution_name=<execution_id>
            filter_str = f"""
            resource.type="cloud_run_job"
            labels."run.googleapis.com/execution_name"="{execution_id}"
            """

            is_done = False
            sent_event_ids = set()
            loop = asyncio.get_running_loop()

            while not is_done:
                if await operation.done():
                    is_done = True

                try:
                    new_logs = await loop.run_in_executor(
                        None,
                        functools.partial(
                            self.logging_client.list_entries,
                            filter_=filter_str,
                            order_by=cloud_logging.DESCENDING,
                            page_size=200,
                        ),
                    )
                    new_logs = sorted(list(new_logs), key=lambda x: x.timestamp)
                except Exception as e:
                    logger.warning(f"Log fetch failed (transient): {e}")
                    new_logs = []

                for entry in new_logs:
                    if entry.insert_id in sent_event_ids:
                        continue

                    sent_event_ids.add(entry.insert_id)
                    payload = entry.payload

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
                    await asyncio.sleep(2)

            # Drain trailing logs: Cloud Logging can delay a few seconds, so the "final" event
            # may appear after operation.done(). Fetch a few more times before closing the stream.
            for _ in range(3):
                await asyncio.sleep(2)
                try:
                    tail_logs = await loop.run_in_executor(
                        None,
                        functools.partial(
                            self.logging_client.list_entries,
                            filter_=filter_str,
                            order_by=cloud_logging.DESCENDING,
                            page_size=200,
                        ),
                    )
                    tail_logs = sorted(list(tail_logs), key=lambda x: x.timestamp)
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
                                except Exception:
                                    pass
                            elif "::CHARM_EVENT::" in line:
                                try:
                                    json_part = line.split("::CHARM_EVENT::")[1].strip()
                                    yield f"data: {json_part}\n\n"
                                except Exception:
                                    pass
                except Exception as e:
                    logger.debug("Trailing log fetch failed: %s", e)

            try:
                await operation.result()
                yield sse_pack("status", "Cloud Job Completed Successfully.")
                yield sse_pack("internal_run_finished", {"exit_code": 0, "duration_ms": 0})
            except Exception as job_error:
                tail_lines = []
                try:
                    final_logs = await loop.run_in_executor(
                        None,
                        functools.partial(
                            self.logging_client.list_entries,
                            filter_=filter_str,
                            order_by=cloud_logging.DESCENDING,
                            page_size=100,
                        ),
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

        except Exception as e:
            logger.exception("Cloud Run Error")
            yield sse_pack("error", f"Cloud Infrastructure Error: {str(e)}")

        finally:
            if job_name:
                skip_cleanup = os.environ.get("CHARM_KEEP_JOB_AFTER_RUN", "").lower() in ("1", "true", "yes")
                if skip_cleanup:
                    logger.info(f"[CloudRun] Keeping job for inspection: {job_name}")
                else:
                    yield sse_pack("status", "Cleaning up resources...")
                    await self.cleanup(job_name)

    async def cleanup(self, job_name: str):
        try:
            request = run_v2.DeleteJobRequest(name=job_name)
            await self.jobs_client.delete_job(request=request)
            logger.info(f"[CloudRun] Deleted job {job_name}")
        except Exception as e:
            logger.warning(f"[CloudRun] Failed to delete job {job_name}: {e}")
