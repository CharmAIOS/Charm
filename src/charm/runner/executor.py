import json
import logging
import os
import shutil
import tempfile
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .backend.base import RunConfig
from .backend.docker import DockerBackend
from .protocol import sse_pack
from .script_builder import BashScriptBuilder

CloudRunBackend: Optional[type[Any]]
try:
    from .backend.cloud_run import CloudRunBackend as _CloudRunBackend

    CloudRunBackend = _CloudRunBackend
except ImportError:
    CloudRunBackend = None

FlyIoBackend: Optional[type[Any]]
try:
    from .backend.fly_io import FlyIoBackend as _FlyIoBackend

    FlyIoBackend = _FlyIoBackend
except ImportError:
    FlyIoBackend = None

logger = logging.getLogger("charm.runner")

TEMP_DIR = tempfile.gettempdir()

# Maps adapter type names to the env var that holds the corresponding image URI.
# The env vars are set by the deploy workflow (deploy-prod.yml / deploy-staging.yml).
# Community adapters installed as plugins can extend this by setting their own
# CHARM_IMAGE_<ADAPTER> env var — the fallback logic below picks them up automatically.
_ADAPTER_IMAGE_ENV: Dict[str, str] = {
    "langchain":  "CHARM_IMAGE_LANGCHAIN",
    "langgraph":  "CHARM_IMAGE_LANGCHAIN",  # LangGraph shares the LangChain image
    "crewai":     "CHARM_IMAGE_CREWAI",
    "openclaw":   "CHARM_IMAGE_OPENCLAW",
    # python / custom / node all fall through to the base image
}

_DEFAULT_IMAGE_FALLBACK = (
    "us-central1-docker.pkg.dev/charm-cloud-runner/charm/runner-base:latest"
)


def _resolve_image(adapter_type: str, custom_image: Optional[str]) -> Optional[str]:
    """Return the Docker image to use for this run.

    Priority order:
    1. ``custom_image`` declared in charm.yaml (agent-level override).
    2. Adapter-specific image from ``CHARM_IMAGE_<ADAPTER>`` env var.
    3. Generic ``CHARM_WORKER_IMAGE`` env var (legacy / single-image deployments).
    4. ``CHARM_IMAGE_BASE`` env var (explicit base image).
    5. Hardcoded fallback (used only in local dev when nothing is configured).
    """
    if custom_image:
        logger.debug("[Executor] Using custom_image override: %s", custom_image)
        return custom_image

    # Adapter-specific lookup — check the known map first, then try a
    # convention-based env var (CHARM_IMAGE_<ADAPTER_TYPE_UPPER>) so community
    # adapters can register their own images without modifying core code.
    env_key = _ADAPTER_IMAGE_ENV.get(adapter_type) or f"CHARM_IMAGE_{adapter_type.upper()}"
    adapter_image = os.getenv(env_key)
    if adapter_image:
        logger.debug(
            "[Executor] Resolved adapter '%s' → image from %s: %s",
            adapter_type, env_key, adapter_image,
        )
        return adapter_image

    # Legacy single-image env var
    worker_image = os.getenv("CHARM_WORKER_IMAGE")
    if worker_image:
        logger.debug("[Executor] Using CHARM_WORKER_IMAGE: %s", worker_image)
        return worker_image

    # Explicit base image env var
    base_image = os.getenv("CHARM_IMAGE_BASE")
    if base_image:
        logger.debug("[Executor] Using CHARM_IMAGE_BASE: %s", base_image)
        return base_image

    logger.debug("[Executor] No image env var found for adapter '%s'; using hardcoded fallback", adapter_type)
    return None  # cloud_run.py will apply its own fallback constant
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
        skills: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        skills = skills or []
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

        use_bundle_local = bundle_local_path is not None and os.path.isfile(bundle_local_path) and isinstance(
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

        # Resolve the Docker image: custom_image > adapter-specific > base fallback.
        # Skip image resolution for local Docker runs — Docker uses whatever image is
        # already pulled locally and _resolve_image is only meaningful for Cloud Run.
        resolved_image = (
            image if isinstance(backend, DockerBackend)
            else _resolve_image(adapter_type, image)
        )

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
            image=resolved_image,
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
