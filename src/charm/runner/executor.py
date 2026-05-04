import json
import logging
import os
import shutil
import tempfile
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .backend.base import ExecutionBackend, RunConfig
from .backend.docker import DockerBackend
from .protocol import EVENT_PREFIX, sse_pack
from .script_builder import BashScriptBuilder

try:
    from .backend.cloud_run import CloudRunBackend
except ImportError:
    CloudRunBackend = None

try:
    from .backend.fly_io import FlyIoBackend
except ImportError:
    FlyIoBackend = None

logger = logging.getLogger("charm.runner")

TEMP_DIR = tempfile.gettempdir()
HOST_CACHE_DIR = os.path.join(TEMP_DIR, "charm_uv_cache")
HOST_ARTIFACTS_ROOT = os.path.join(TEMP_DIR, "charm_artifacts_buffer")


class CharmDockerExecutor:
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")

        os.makedirs(HOST_CACHE_DIR, exist_ok=True)
        os.makedirs(HOST_ARTIFACTS_ROOT, exist_ok=True)

        # Lazy init backends - don't attempt Docker on staging/prod
        self._local_docker_backend = None
        self.cloud_run_backend = self._safe_cloud_run_backend()
        self.daemon_backend = self._safe_flyio_backend()

    @property
    def local_docker_backend(self):
        if self._local_docker_backend is None:
            self._local_docker_backend = DockerBackend()
        return self._local_docker_backend

    def _safe_cloud_run_backend(self) -> Optional[Any]:
        if not CloudRunBackend:
            return None
        try:
            return CloudRunBackend()
        except Exception as e:
            logger.debug("Cloud Run backend unavailable (local dev ok): %s", e)
            return None

    def _safe_flyio_backend(self) -> Optional[Any]:
        if not FlyIoBackend:
            return None
        try:
            return FlyIoBackend()
        except Exception as e:
            logger.debug("Fly.io backend unavailable (local dev ok): %s", e)
            return None

    async def run(
        self,
        agent_id: str,
        input_payload: Dict[str, Any],
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        history: List[Dict[str, str]],
        state_snapshot: str = "",
        thread_id: Optional[str] = None,
        local_source_path: Optional[str] = None,
        bundle_local_path: Optional[str] = None,
        bundle_gcs_path: Optional[str] = None,
        supabase_client: Any = None,
        image: Optional[str] = None,
        adapter_type: str = "python",
        lifecycle: str = "serverless",
        timeout_seconds: Optional[int] = None,
        skills: List[Dict[str, Any]] = [],
    ) -> AsyncGenerator[str, None]:
        run_timestamp = int(time.time())
        run_id = f"{agent_id}_{run_timestamp}"
        host_artifact_path = os.path.join(HOST_ARTIFACTS_ROOT, run_id)
        os.makedirs(host_artifact_path, exist_ok=True)

        if thread_id:
            input_payload["__charm_thread_id__"] = thread_id

        if state_snapshot:
            input_payload["__charm_state__"] = state_snapshot

        # Pass chat history to the agent
        if history:
            input_payload["__charm_history__"] = history
            input_payload["history"] = history
            # Also pass via env var for stability
            import json as json_module
            env_vars["CHARM_HISTORY"] = json_module.dumps(history)

        user_id = env_vars.get("CHARM_USER_ID", "local_dev")
        # Daemon agents share a single workspace across all threads so OpenClaw
        # memory persists regardless of which conversation the user is in.
        # Serverless/interactive agents keep per-thread isolation.
        if lifecycle == "daemon":
            env_vars["CHARM_WORKSPACE_DIR"] = f"/workspace/{user_id}/{agent_id}/daemon_shared"
        else:
            thread_id_val = thread_id or "default_thread"
            env_vars["CHARM_WORKSPACE_DIR"] = f"/workspace/{user_id}/{agent_id}/{thread_id_val}"

        if bundle_local_path and os.path.isfile(bundle_local_path):
            env_vars["CHARM_BUNDLE_LOCAL_PATH"] = "/app/bundle_mount/" + os.path.basename(bundle_local_path)

        # Dynamic backend dispatch based on environment and lifecycle
        if self.env in ["production", "staging"]:
            if lifecycle == "daemon":
                logger.info(f"[{run_id}] Dispatching to Daemon Infrastructure")
                if self.daemon_backend:
                    backend = self.daemon_backend
                else:
                    yield sse_pack(
                        "error",
                        "Daemon infrastructure (Fly.io/K8s) is not configured on this environment.",
                    )
                    return
            else:
                logger.info(f"[{run_id}] Dispatching to Serverless Infrastructure")
                if self.cloud_run_backend:
                    backend = self.cloud_run_backend
                else:
                    yield sse_pack(
                        "error", "Serverless infrastructure (Cloud Run) is not configured."
                    )
                    return
        else:
            # Local development: respect lifecycle so dev mirrors staging exactly.
            # daemon → Fly.io backend (same as staging); everything else → Docker.
            if lifecycle == "daemon" and self.daemon_backend:
                logger.info(f"[{run_id}] [Local] Dispatching to Daemon Infrastructure (Fly.io)")
                backend = self.daemon_backend
            else:
                backend = self.local_docker_backend

        if bundle_gcs_path and not isinstance(backend, DockerBackend):
            env_vars["CHARM_BUNDLE_GCS_PATH"] = "/workspace/" + bundle_gcs_path.lstrip("/")

        force_bundle_download = os.environ.get("CHARM_FORCE_BUNDLE_DOWNLOAD", "").lower() in ("1", "true", "yes")
        should_mount_local = (
            bool(local_source_path)
            and isinstance(backend, DockerBackend)
            and not force_bundle_download
        )

        use_file_input = False
        if isinstance(backend, DockerBackend):
            try:
                input_path = os.path.join(host_artifact_path, "input.json")
                with open(input_path, "w", encoding="utf-8") as f:
                    json.dump(input_payload, f, ensure_ascii=False)
                use_file_input = True
                logger.info(f"Payload written to {input_path} for Docker mount.")
            except Exception as e:
                logger.error(f"Failed to write input.json: {e}")

        use_bundle_local = bool(bundle_local_path) and os.path.isfile(bundle_local_path) and isinstance(
            backend, DockerBackend
        )
        use_bundle_gcs = bool(bundle_gcs_path) and not isinstance(backend, DockerBackend)

        script_content = BashScriptBuilder.generate(
            env_vars=env_vars,
            file_urls=file_urls,
            input_payload=input_payload,
            use_local_mount=should_mount_local,
            use_bundle_local=use_bundle_local,
            use_bundle_gcs=use_bundle_gcs,
            use_file_input=use_file_input,
            adapter_type=adapter_type,
            skills=skills,
        )

        # Local SDK override for dev: mount the host SDK source tree so container
        # picks up code changes without requiring an image rebuild.
        local_sdk_host_path = os.environ.get("LOCAL_SDK_HOST_PATH", "").strip() or None
        if local_sdk_host_path and not os.path.isdir(local_sdk_host_path):
            logger.warning("[Executor] LOCAL_SDK_HOST_PATH=%s is not a directory; ignoring", local_sdk_host_path)
            local_sdk_host_path = None

        config = RunConfig(
            agent_id=agent_id,
            run_id=run_id,
            input_payload=input_payload,
            env_vars=env_vars,
            file_urls=file_urls,
            script_content=script_content,
            host_artifact_path=host_artifact_path,
            host_cache_dir=HOST_CACHE_DIR,
            local_source_path=local_source_path if should_mount_local else None,
            local_sdk_path=local_sdk_host_path if isinstance(backend, DockerBackend) else None,
            bundle_local_path=bundle_local_path if use_bundle_local else None,
            image=image,
            lifecycle=lifecycle,
            timeout_seconds=timeout_seconds,
            supabase_client=supabase_client,
        )

        try:
            async for log in backend.stream_logs(config):
                if "internal_artifact_found" in log:
                    yield log
                    continue
                yield log

        except Exception as e:
            logger.exception("Orchestrator Error")
            yield sse_pack("error", f"Orchestrator Error: {e}")
        finally:
            await backend.cleanup(run_id)
            shutil.rmtree(host_artifact_path, ignore_errors=True)
