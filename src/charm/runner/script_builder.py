import base64
import hashlib
import json
import os
import shlex
from typing import Any, Dict, List

from .protocol import EVENT_PREFIX
from .skill_installer import SkillInstaller


class BashScriptBuilder:
    @staticmethod
    def generate(
        env_vars: Dict[str, str],
        file_urls: Dict[str, str],
        input_payload: Dict[str, Any],
        use_local_mount: bool = False,
        use_bundle_local: bool = False,
        use_bundle_gcs: bool = False,
        use_file_input: bool = False,
        adapter_type: str = "python",
        skills: List[Dict[str, Any]] = None,
    ) -> str:
        skills = skills or []
        
        # Environment Variables
        env_file_lines = []
        for k, v in env_vars.items():
            # Escape newlines and quotes to prevent bash errors
            safe_val = str(v).replace("\n", "\\n").replace('"', '\\"')
            env_file_lines.append(f'{k}="{safe_val}"')
        b64_env_content = base64.b64encode("\n".join(env_file_lines).encode()).decode()

        # File Downloads
        dl_cmds = []
        if file_urls:
            for f, u in file_urls.items():
                dl_cmds.append(f"curl -s -L {shlex.quote(u)} -o {shlex.quote(os.path.basename(f))}")
        dl_block = "\n".join(dl_cmds) if dl_cmds else "true"

        # Source Code Setup
        if use_local_mount:
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Local Source Code..."}}'
            [ ! -d "/app/local_source_mount" ] && exit 1
            cp -rT /app/local_source_mount/. .
            """
        elif use_bundle_local:
            # Runner downloaded bundle and mounted it (local dev workaround when curl gets wrong response)
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Runner-Downloaded Bundle..."}}'
            if [ -z "$CHARM_BUNDLE_LOCAL_PATH" ] || [ ! -f "$CHARM_BUNDLE_LOCAL_PATH" ]; then
              echo '{EVENT_PREFIX}{{"type":"thinking","content":"Bundle file not found at CHARM_BUNDLE_LOCAL_PATH."}}'
              exit 1
            fi
            cp "$CHARM_BUNDLE_LOCAL_PATH" bundle.tar.gz
            if ! tar -xzf bundle.tar.gz --no-same-owner; then
              echo '{EVENT_PREFIX}{{"type":"thinking","content":"Bundle extract failed (corrupt or not gzip)."}}'
              rm -f bundle.tar.gz
              exit 1
            fi
            rm -f bundle.tar.gz
            if [ ! -f charm.yaml ] && [ $(ls -A | wc -l) -eq 1 ] && [ -d "$(ls -A)" ]; then
                cd "$(ls -A)" || true
            fi
            """
        elif use_bundle_gcs:
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Runner-Uploaded Bundle (GCS)..."}}'
            if [ -z "$CHARM_BUNDLE_GCS_PATH" ] || [ ! -f "$CHARM_BUNDLE_GCS_PATH" ]; then
              echo '{EVENT_PREFIX}{{"type":"thinking","content":"Bundle file not found at CHARM_BUNDLE_GCS_PATH."}}'
              exit 1
            fi
            cp "$CHARM_BUNDLE_GCS_PATH" bundle.tar.gz
            if ! tar -xzf bundle.tar.gz --no-same-owner; then
              echo '{EVENT_PREFIX}{{"type":"thinking","content":"Bundle extract failed (corrupt or not gzip)."}}'
              rm -f bundle.tar.gz
              exit 1
            fi
            rm -f bundle.tar.gz
            if [ ! -f charm.yaml ] && [ $(ls -A | wc -l) -eq 1 ] && [ -d "$(ls -A)" ]; then
                cd "$(ls -A)" || true
            fi
            """
        else:
            source_setup_block = f"""
            echo '{EVENT_PREFIX}{{"type":"error","content":"No bundle source available. Ensure GCS bundle path is configured for staging/prod or bundle_local_path for local dev."}}'
            exit 1
            """

        # Dependency Installation Logic (Polyglot)
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

        install_python_deps_block = f"""
        if [ -f pyproject.toml ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing Python dependencies..."}}'
            uv pip install -q -r pyproject.toml || uv pip install -q .
        elif [ -f requirements.txt ]; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Installing Python dependencies..."}}'
            uv pip install -q -r requirements.txt
        fi
        """

        # SDK Setup
        # When LOCAL_SDK_HOST_PATH is set (dev mode), the Docker backend mounts the
        # local Charm SDK source tree at /mnt/local_sdk.  Prefer it via PYTHONPATH so
        # code changes are reflected immediately without rebuilding the image or running
        # pip (which fails on read-only mounts due to .egg-info write attempts).
        sdk_install_block = f"""
        if [ -d "/mnt/local_sdk/src" ]; then
            export PYTHONPATH="/mnt/local_sdk/src:$PYTHONPATH"
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Local Charm SDK (dev override)."}}'
        elif [ -d "/mnt/local_sdk" ]; then
            export PYTHONPATH="/mnt/local_sdk:$PYTHONPATH"
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Local Charm SDK (dev override)."}}'
        elif python -c "import charm" 2>/dev/null; then
            echo '{EVENT_PREFIX}{{"type":"status","content":"Using Pre-installed Charm SDK."}}'
        else
            echo '{EVENT_PREFIX}{{"type":"status","content":"SDK not found. Installing from PyPI..."}}'
            uv pip install --upgrade "charmos[runner]>=0.4.20"
        fi
        """

        # Skill Installation Block
        skill_setup_block = SkillInstaller.generate_skill_install_block(skills)

        # [Removed] memory_hydration_block
        # Reason: Now using GCS Mount, files are already there, no need to inject via env vars.

        # Execution Command Selection
        if adapter_type == "node":
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Starting Node.js Agent..."}'
            npm start
            """
        elif adapter_type == "openclaw":
            # OpenClaw Execution Path
            b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()

            # Python script that patches ~/.openclaw/openclaw.json to route LLM calls
            # through the Charm proxy.  We embed it base64-encoded so it can be piped
            # to `python3` inside the container without heredoc quoting issues.
            # This runs *before* `charm run` so it is SDK-version-independent.
            _oc_proxy_patch_py = """\
import json, os, pathlib, sys
home = os.environ.get("HOME", "/root")
cfg_path = pathlib.Path(home) / ".openclaw" / "openclaw.json"
try:
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
except Exception:
    cfg = {}
proxy_base = os.environ.get("CHARM_LLM_PROXY_BASE", "")
proxy_key  = os.environ.get("CHARM_LLM_PROXY_KEY", "")
if not proxy_base or not proxy_key:
    sys.exit(0)
try:
    raw = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "openai/gpt-4o")
    model_id = raw.split("/", 1)[-1] if "/" in raw else raw
except Exception:
    model_id = "gpt-4o"
cfg.setdefault("agents", {}).setdefault("defaults", {})["model"] = {"primary": "openai/" + model_id}
cfg.setdefault("models", {}).setdefault("providers", {})["openai"] = {
    "baseUrl": proxy_base, "apiKey": proxy_key,
    "models": [{"id": model_id, "name": model_id}],
}
cfg_path.parent.mkdir(parents=True, exist_ok=True)
cfg_path.write_text(json.dumps(cfg, indent=2))
auth_dir = pathlib.Path(home) / ".openclaw" / "agents" / "main" / "agent"
auth_dir.mkdir(parents=True, exist_ok=True)
(auth_dir / "auth-profiles.json").write_text(json.dumps({
    "version": 1,
    "profiles": {"openai:api": {"type": "api_key", "provider": "openai", "key": proxy_key}},
}, indent=2))
print("OpenClaw LLM proxy configured:", proxy_base)
"""
            b64_oc_proxy_patch = base64.b64encode(_oc_proxy_patch_py.encode()).decode()

            execution_cmd = f"""
            echo '::CHARM_EVENT::{{"type":"status","content":"Booting OpenClaw Host..."}}'
            INPUT_JSON="$(echo {b64_payload} | base64 -d)"
            export CHARM_SESSION_MODE="true"

            # Ensure openclaw is onboarded (creates ~/.openclaw/openclaw.json)
            OPENCLAW_HOME="${{HOME:-/root}}/.openclaw"
            if [ ! -f "$OPENCLAW_HOME/openclaw.json" ]; then
                openclaw onboard --non-interactive --accept-risk 2>/dev/null || true
            fi

            # Patch openclaw.json with Charm LLM proxy config.
            # Runs before `charm run` so it is independent of the Charm SDK version
            # installed in the image — the proxy baseUrl is always applied.
            echo '{b64_oc_proxy_patch}' | base64 -d | python3

            # Launch using Charm SDK to load OpenClawAdapter.
            charm run . --json "$INPUT_JSON"
            """
        elif use_file_input:
            execution_cmd = """
            echo '::CHARM_EVENT::{"type":"status","content":"Running Agent (File Mode)..."}'
            python3 -c "import sys, subprocess, pathlib; \
            json_payload = pathlib.Path('/app/artifacts_mount/input.json').read_text(encoding='utf-8'); \
            sys.exit(subprocess.run(['charm', 'run', '.', '--json', json_payload]).returncode)"
            """
        else:
            b64_payload = base64.b64encode(json.dumps(input_payload).encode()).decode()
            execution_cmd = f"""
            echo '::CHARM_EVENT::{{"type":"status","content":"Running Agent (Cloud Mode)..."}}'
            INPUT_JSON="$(echo {b64_payload} | base64 -d)"
            charm run . --json "$INPUT_JSON"
            """

        # Rollback restore block (Agentic OTA — CHARM_ROLLBACK_SNAPSHOT_PATH)
        # This block is a no-op on normal and upgrade runs.  When the /v1/rollback
        # runner path injects CHARM_ROLLBACK_SNAPSHOT_PATH, the container extracts
        # the snapshot tarball back into the workspace and exits 0 — the cleanup trap
        # emits internal_run_finished so the runner knows the restore succeeded.
        # The block runs before source setup so no bundle download is required.
        rollback_block = """        # Rollback workspace restore (Agentic OTA)
        if [ -n "$CHARM_ROLLBACK_SNAPSHOT_PATH" ]; then
            echo '::CHARM_EVENT::{"type":"status","content":"Restoring workspace from snapshot..."}'
            mkdir -p "$CHARM_WORKSPACE_DIR"
            # Clear current workspace contents while preserving the .snapshots directory.
            find "$CHARM_WORKSPACE_DIR" -mindepth 1 -maxdepth 1 ! -name '.snapshots' -exec rm -rf {} +
            if [ -f "$CHARM_ROLLBACK_SNAPSHOT_PATH" ]; then
                tar -xzf "$CHARM_ROLLBACK_SNAPSHOT_PATH" -C "$CHARM_WORKSPACE_DIR"
                echo '::CHARM_EVENT::{"type":"status","content":"Workspace restored successfully."}'
                exit 0
            else
                echo '::CHARM_EVENT::{"type":"error","content":"Snapshot not found: $CHARM_ROLLBACK_SNAPSHOT_PATH"}'
                exit 1
            fi
        fi"""

        # Pre-upgrade workspace snapshot block (Agentic OTA Rollback — Gap 3)
        # This block is a no-op on normal runs.  When CHARM_UPGRADE_SNAPSHOT_VERSION is
        # set (injected by the /v1/upgrade runner path) the workspace is tarred into
        # $CHARM_WORKSPACE_DIR/.snapshots/<old_version>.tar.gz before the merge begins,
        # giving operators a one-command rollback path.
        snapshot_block = """        # Pre-upgrade workspace snapshot (Agentic OTA)
        if [ -n "$CHARM_UPGRADE_SNAPSHOT_VERSION" ]; then
            echo '::CHARM_EVENT::{"type":"status","content":"Creating workspace snapshot..."}'
            SNAPSHOT_DIR="$CHARM_WORKSPACE_DIR/.snapshots"
            mkdir -p "$SNAPSHOT_DIR"
            SNAPSHOT_ARCHIVE="$SNAPSHOT_DIR/${CHARM_UPGRADE_SNAPSHOT_VERSION}.tar.gz"
            # Only compress if the workspace has content beyond the .snapshots dir itself.
            if [ -n "$(ls -A "$CHARM_WORKSPACE_DIR" 2>/dev/null | grep -v '^\\.snapshots$')" ]; then
                tar -czf "$SNAPSHOT_ARCHIVE" \\
                    --exclude='.snapshots' \\
                    -C "$CHARM_WORKSPACE_DIR" . 2>/dev/null || true
                echo '::CHARM_EVENT::{"type":"status","content":"Workspace snapshot saved."}'
            else
                echo '::CHARM_EVENT::{"type":"status","content":"Workspace empty — snapshot skipped."}'
            fi
        fi"""

        # Cleanup & Persistence Logic
        cleanup_function = f"""
        function cleanup {{
            EXIT_CODE=$?
            echo '::CHARM_EVENT::{{"type":"status","content":"Saving Execution Context..."}}'
            
            # [Removed] Memory Sync logic (curl POST to store)
            # Reason: GCS Fuse writes automatically, no need to manually sync via API.
            
            # --- Artifact Upload (Preserved, used to download generated PDFs/Images) ---
            if [ ! -z "$CHARM_ARTIFACT_UPLOAD_URL" ]; then
                tar -czf output_artifacts.tar.gz \\
                    --exclude='./.*' \\
                    --exclude='__pycache__' \\
                    --exclude='node_modules' \\
                    --exclude='skills' \\
                    --newer .charm_snapshot .

                curl -s -X PUT -T output_artifacts.tar.gz -H "Content-Type: application/gzip" "$CHARM_ARTIFACT_UPLOAD_URL"
            fi
            
            echo '::CHARM_EVENT::{{"type":"internal_run_finished","content":{{"exit_code":'"$EXIT_CODE"',"duration_ms":0}}}}'
        }}
        trap cleanup EXIT
        """

        # Assemble Final Script
        script = f"""
        set -e
        (while true; do echo '::CHARM_EVENT::{{"type":"thinking","content":"..."}}'; sleep 5; done) &
        HEARTBEAT_PID=$!
        
        {cleanup_function}
        
        trap "kill $HEARTBEAT_PID 2>/dev/null; cleanup" EXIT

        mkdir -p agent_code && cd agent_code

        {rollback_block}

        {source_setup_block}

        echo "{b64_env_content}" | base64 -d > .env
        {dl_block}

        mkdir -p "$CHARM_WORKSPACE_DIR"
        mkdir -p /app/artifacts_mount

        {snapshot_block}

        # Install Dependencies
        {install_node_deps_block}
        {install_python_deps_block}
        
        # Install Skills (Dynamic Loading)
        {skill_setup_block}
        
        # Inject Global Memory (User Profile)
        # [Removed] MEMORY_FILE_PATH setup and injection

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
