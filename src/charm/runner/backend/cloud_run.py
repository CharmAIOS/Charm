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

    async def _create_job(self, job_id: str, config: RunConfig) -> str:
        b64_script = base64.b64encode(config.script_content.encode("utf-8")).decode("utf-8")

        env_vars = [
            {"name": "PYTHONUNBUFFERED", "value": "1"},
            {"name": "CHARM_BOOTSTRAP_SCRIPT", "value": b64_script},
            *[{"name": k, "value": str(v)} for k, v in config.env_vars.items()],
        ]

        default_fallback = (
            "us-central1-docker.pkg.dev/charm-cloud-runner/charm/runner-standard:latest"
        )
        worker_image = config.image or os.getenv("CHARM_WORKER_IMAGE", default_fallback)

        logger.info(f"[CloudRun] Target Image resolved to: {worker_image}")

        job = run_v2.Job()
        job.template.template.containers = [
            {
                "image": worker_image,
                "command": ["/bin/bash", "-c"],
                "args": ["echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash"],
                "env": env_vars,
                "resources": {"limits": {"memory": "2Gi", "cpu": "1000m"}},
            }
        ]

        job.template.task_count = 1
        job.template.template.max_retries = 0
        job.template.task_count = 1
        job.template.template.max_retries = 0
        job.template.template.timeout = "3600s"

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
            logger.info(f"[CloudRun] Tailing logs for execution: {execution_name}")

            filter_str = f"""
            resource.type="cloud_run_job"
            labels."run.googleapis.com/execution_name"="{execution_name.split("/")[-1]}"
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
                            page_size=50,
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
                                json_part = line.split(EVENT_PREFIX)[1]
                                yield f"data: {json_part}\n\n"
                            except:
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

            try:
                await operation.result()
                yield sse_pack("status", "Cloud Job Completed Successfully.")
                yield sse_pack("internal_run_finished", {"exit_code": 0, "duration_ms": 0})
            except Exception as job_error:
                yield sse_pack("error", f"Job Failed: {str(job_error)}")

        except Exception as e:
            logger.exception("Cloud Run Error")
            yield sse_pack("error", f"Cloud Infrastructure Error: {str(e)}")

        finally:
            if job_name:
                yield sse_pack("status", "Cleaning up resources...")
                await self.cleanup(job_name)

    async def cleanup(self, job_name: str):
        try:
            request = run_v2.DeleteJobRequest(name=job_name)
            await self.jobs_client.delete_job(request=request)
            logger.info(f"[CloudRun] Deleted job {job_name}")
        except Exception as e:
            logger.warning(f"[CloudRun] Failed to delete job {job_name}: {e}")
