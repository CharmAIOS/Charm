import asyncio
import base64
import logging
import os
import textwrap
from typing import AsyncGenerator, Optional, Tuple

import aiohttp

from ...runner.protocol import sse_pack
from .base import ExecutionBackend, RunConfig
from .fly_api_client import FlyApiClient

logger = logging.getLogger("charm.runner.fly_io")


MACHINE_POLL_INTERVAL = 3
MACHINE_POLL_MAX_ATTEMPTS = 40  # 40 × 3s = 120s — image pull can take ~45-60s on first boot
MACHINE_HEALTH_POLL_INTERVAL = 3
MACHINE_HEALTH_MAX_ATTEMPTS = 40  # 40 × 3s = 120s — bootstrap + image pull can exceed 60s on first boot
MACHINE_TRANSITIONAL_STATES = ("stopping", "restarting", "replacing")
DAEMON_AGENT_PORT = 8000


class FlyIoBackend(ExecutionBackend):

    def __init__(self):
        self.api_token = os.getenv("FLY_API_TOKEN")
        self.app_name = os.getenv("FLY_APP_NAME")
        self.region = os.getenv("FLY_REGION", "sjc")

        self.api: Optional[FlyApiClient]
        if self.api_token and self.app_name:
            self.api = FlyApiClient(self.api_token, self.app_name, self.region)
        else:
            self.api = None

        if not self.app_name:
            logger.warning("FLY_APP_NAME is not set. Daemon mode will fail.")



    def _load_daemon_record(self, supabase_client, agent_id: str, user_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Returns (machine_id, volume_id, status)."""
        try:
            result = (
                supabase_client.table("daemon_machines")
                .select("fly_machine_id,fly_volume_id,status")
                .eq("agent_id", agent_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return (
                    result.data.get("fly_machine_id"),
                    result.data.get("fly_volume_id"),
                    result.data.get("status"),
                )
        except Exception as e:
            logger.warning("Failed to load daemon record: %s", e)
        return None, None, None

    def _save_daemon_record(self, supabase_client, agent_id: str, user_id: str, machine_id: str, volume_id: Optional[str]):
        try:
            supabase_client.table("daemon_machines").upsert(
                {
                    "agent_id": agent_id,
                    "user_id": user_id,
                    "fly_machine_id": machine_id,
                    "fly_volume_id": volume_id,
                    "status": "running",
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to persist daemon record: %s", e)

    def _generate_bootstrap_script(self) -> str:
        """Return a base64-encoded bootstrap bash script.

        The script writes a minimal Python HTTP server to /tmp/cd.py then
        exec-replaces itself with it.  The server exposes:
          GET  /health  → {"status":"ok"}
          POST /job     → run openclaw agent, stream SSE back
        """
        daemon_server_py = textwrap.dedent(r"""
            import json,subprocess,os
            from http.server import HTTPServer,BaseHTTPRequestHandler
            SECRET=os.environ.get("RUNNER_DAEMON_SECRET","")
            def _resolve_snapshot_archive(snap_path,snap_url,snap_paths_json):
                import json as _json,os as _os,urllib.request as _urlreq
                paths=[]
                if snap_path:
                    paths.append(snap_path)
                if snap_paths_json:
                    try:
                        extra=_json.loads(snap_paths_json)
                        if isinstance(extra,list):
                            for p in extra:
                                if isinstance(p,str) and p and p not in paths:
                                    paths.append(p)
                    except Exception:
                        pass
                for p in paths:
                    if p and _os.path.isfile(p):
                        return p
                if snap_url and paths:
                    target=paths[0]
                    try:
                        _os.makedirs(_os.path.dirname(target),exist_ok=True)
                        with _urlreq.urlopen(snap_url,timeout=180) as resp:
                            data=resp.read()
                        with open(target,"wb") as out:
                            out.write(data)
                        if _os.path.isfile(target):
                            return target
                    except Exception:
                        pass
                return None
            def _openclaw_home():
                return os.path.join(os.path.expanduser("~"),".openclaw")
            def _snapshot_has_state(ws):
                try:
                    for name in os.listdir(ws):
                        if name!=".snapshots":
                            return True
                except Exception:
                    pass
                oc=_openclaw_home()
                try:
                    return os.path.isdir(oc) and bool(os.listdir(oc))
                except Exception:
                    return False
            def _clear_openclaw_home():
                import shutil
                oc=_openclaw_home()
                if not os.path.isdir(oc):
                    return
                for name in os.listdir(oc):
                    pth=os.path.join(oc,name)
                    if os.path.isdir(pth):
                        shutil.rmtree(pth,ignore_errors=True)
                    else:
                        try:os.remove(pth)
                        except Exception:pass
            def _apply_snapshot_restore(tf,ws):
                import shutil,tempfile
                names=tf.getnames()
                prefixed=any(n.startswith("workspace/") or n.startswith("openclaw/") for n in names)
                if not prefixed:
                    tf.extractall(ws)
                    return
                oc=_openclaw_home()
                os.makedirs(oc,exist_ok=True)
                _clear_openclaw_home()
                with tempfile.TemporaryDirectory() as tmp:
                    tf.extractall(tmp)
                    wsrc=os.path.join(tmp,"workspace")
                    if os.path.isdir(wsrc):
                        for name in os.listdir(wsrc):
                            src=os.path.join(wsrc,name)
                            dst=os.path.join(ws,name)
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst,ignore_errors=True)
                                shutil.copytree(src,dst)
                            else:
                                shutil.copy2(src,dst)
                    osrc=os.path.join(tmp,"openclaw")
                    if os.path.isdir(osrc):
                        for name in os.listdir(osrc):
                            src=os.path.join(osrc,name)
                            dst=os.path.join(oc,name)
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst,ignore_errors=True)
                                shutil.copytree(src,dst)
                            else:
                                shutil.copy2(src,dst)
            class H(BaseHTTPRequestHandler):
                def log_message(self,*a):pass
                def do_GET(self):
                    if self.path=="/health":
                        b=b'{"status":"ok"}'
                        self.send_response(200)
                        self.send_header("Content-Type","application/json")
                        self.send_header("Content-Length",str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                    else:
                        self.send_response(404)
                        self.end_headers()
                def do_POST(self):
                    if self.path=="/restore":
                        if SECRET and self.headers.get("X-Daemon-Secret")!=SECRET:
                            self.send_response(401)
                            self.end_headers()
                            return
                        try:
                            n=int(self.headers.get("Content-Length",0))
                            p=json.loads(self.rfile.read(n))
                        except Exception:
                            self.send_response(400)
                            self.end_headers()
                            return
                        ws=p.get("workspace","/workspace/agent_code")
                        snap_path=p.get("snapshot_path","")
                        snap_url=p.get("snapshot_url","")
                        snap_paths_json=p.get("snapshot_paths_json","")
                        self.send_response(200)
                        self.send_header("Content-Type","text/event-stream")
                        self.send_header("Cache-Control","no-cache")
                        self.send_header("X-Accel-Buffering","no")
                        self.end_headers()
                        def emit(d):
                            try:
                                self.wfile.write(("data: "+d+"\n\n").encode())
                                self.wfile.flush()
                            except Exception:pass
                        import shutil,tarfile
                        emit(json.dumps({"type":"status","content":"Restoring workspace from snapshot..."}))
                        os.makedirs(ws,exist_ok=True)
                        for name in os.listdir(ws):
                            if name==".snapshots":continue
                            pth=os.path.join(ws,name)
                            if os.path.isdir(pth):shutil.rmtree(pth,ignore_errors=True)
                            else:
                                try:os.remove(pth)
                                except Exception:pass
                        _clear_openclaw_home()
                        resolved=_resolve_snapshot_archive(snap_path,snap_url,snap_paths_json)
                        if resolved:
                            with tarfile.open(resolved,"r:gz") as tf:
                                _apply_snapshot_restore(tf,ws)
                            emit(json.dumps({"type":"status","content":"Workspace restored successfully."}))
                            emit(json.dumps({"type":"final","content":"ROLLBACK_RESTORE_COMPLETE"}))
                            emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":0}}))
                        else:
                            emit(json.dumps({"type":"error","content":"Snapshot not found: "+snap_path}))
                            emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":1}}))
                        return
                    if self.path!="/job":
                        self.send_response(404)
                        self.end_headers()
                        return
                    if SECRET and self.headers.get("X-Daemon-Secret")!=SECRET:
                        self.send_response(401)
                        self.end_headers()
                        return
                    try:
                        n=int(self.headers.get("Content-Length",0))
                        p=json.loads(self.rfile.read(n))
                    except Exception:
                        self.send_response(400)
                        self.end_headers()
                        return
                    msg=p.get("message","")
                    ws=p.get("workspace","/workspace/agent_code")
                    agent=p.get("agent","main")
                    burl=p.get("bundle_url","")
                    xenv=p.get("env",{})
                    snap_path=xenv.get("CHARM_ROLLBACK_SNAPSHOT_PATH","")
                    snap_url=xenv.get("CHARM_ROLLBACK_SNAPSHOT_URL","")
                    snap_paths_json=xenv.get("CHARM_ROLLBACK_SNAPSHOT_PATHS","")
                    if snap_path or snap_url or snap_paths_json:
                        self.send_response(200)
                        self.send_header("Content-Type","text/event-stream")
                        self.send_header("Cache-Control","no-cache")
                        self.send_header("X-Accel-Buffering","no")
                        self.end_headers()
                        def emit(d):
                            try:
                                self.wfile.write(("data: "+d+"\n\n").encode())
                                self.wfile.flush()
                            except Exception:pass
                        import shutil,tarfile
                        emit(json.dumps({"type":"status","content":"Restoring workspace from snapshot..."}))
                        os.makedirs(ws,exist_ok=True)
                        for name in os.listdir(ws):
                            if name==".snapshots":continue
                            pth=os.path.join(ws,name)
                            if os.path.isdir(pth):shutil.rmtree(pth,ignore_errors=True)
                            else:
                                try:os.remove(pth)
                                except Exception:pass
                        _clear_openclaw_home()
                        resolved=_resolve_snapshot_archive(snap_path,snap_url,snap_paths_json)
                        if resolved:
                            with tarfile.open(resolved,"r:gz") as tf:
                                _apply_snapshot_restore(tf,ws)
                            emit(json.dumps({"type":"status","content":"Workspace restored successfully."}))
                            emit(json.dumps({"type":"final","content":"ROLLBACK_RESTORE_COMPLETE"}))
                            emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":0}}))
                        else:
                            emit(json.dumps({"type":"error","content":"Snapshot not found: "+snap_path}))
                            emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":1}}))
                        return
                    self.send_response(200)
                    self.send_header("Content-Type","text/event-stream")
                    self.send_header("Cache-Control","no-cache")
                    self.send_header("X-Accel-Buffering","no")
                    self.end_headers()
                    def emit(d):
                        try:
                            self.wfile.write(("data: "+d+"\n\n").encode())
                            self.wfile.flush()
                        except Exception:pass
                    marker=os.path.join(ws,".charm_installed")
                    if burl and not os.path.isfile(marker):
                        emit(json.dumps({"type":"status","content":"Installing agent bundle..."}))
                        try:
                            import urllib.request,tarfile,io
                            os.makedirs(ws,exist_ok=True)
                            with urllib.request.urlopen(burl,timeout=60) as r:
                                data=r.read()
                            with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as t:
                                t.extractall(ws)
                            open(marker,"w").close()
                            emit(json.dumps({"type":"status","content":"Agent bundle ready."}))
                        except Exception as e:
                            emit(json.dumps({"type":"error","content":"Bundle setup failed: "+str(e)}))
                            return
                    env={**os.environ,**xenv,"CHARM_WORKSPACE_DIR":ws}
                    upgrade_snap_ver=xenv.get("CHARM_UPGRADE_SNAPSHOT_VERSION","")
                    if upgrade_snap_ver:
                        import tarfile as _tarfile
                        snap_dir=os.path.join(ws,".snapshots")
                        os.makedirs(snap_dir,exist_ok=True)
                        snap_archive=os.path.join(snap_dir,upgrade_snap_ver+".tar.gz")
                        oc_home=_openclaw_home()
                        if os.path.isfile(snap_archive):
                            emit(json.dumps({"type":"status","content":"Workspace snapshot saved."}))
                        elif _snapshot_has_state(ws):
                            emit(json.dumps({"type":"status","content":"Creating workspace snapshot..."}))
                            try:
                                with _tarfile.open(snap_archive,"w:gz") as tf:
                                    try:
                                        for name in os.listdir(ws):
                                            if name==".snapshots":
                                                continue
                                            path=os.path.join(ws,name)
                                            tf.add(path,arcname="workspace/"+name)
                                    except Exception:
                                        pass
                                    if os.path.isdir(oc_home):
                                        try:
                                            for name in os.listdir(oc_home):
                                                path=os.path.join(oc_home,name)
                                                tf.add(path,arcname="openclaw/"+name)
                                        except Exception:
                                            pass
                                emit(json.dumps({"type":"status","content":"Workspace snapshot saved."}))
                            except Exception as e:
                                emit(json.dumps({"type":"error","content":"Snapshot creation failed: "+str(e)}))
                                emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":1}}))
                                return
                        else:
                            emit(json.dumps({"type":"status","content":"Workspace empty — snapshot skipped."}))
                    # Write openclaw.json so openclaw routes LLM calls through the Charm proxy.
                    # CHARM_LLM_PROXY_BASE and CHARM_LLM_PROXY_KEY are forwarded in xenv.
                    proxy_base=env.get("CHARM_LLM_PROXY_BASE","").strip()
                    proxy_key=env.get("CHARM_LLM_PROXY_KEY","").strip()
                    model_id=env.get("CHARM_LLM_MODEL","gpt-4o").strip()
                    if proxy_base and proxy_key:
                        import pathlib
                        oc_home=os.path.join(os.path.expanduser("~"),".openclaw")
                        pathlib.Path(oc_home).mkdir(parents=True,exist_ok=True)
                        oc_cfg={
                            "agents":{"defaults":{"model":{"primary":"litellm/"+model_id}}},
                            "models":{"providers":{"litellm":{"baseUrl":proxy_base,"apiKey":proxy_key,"api":"openai-completions","models":[{"id":model_id,"name":model_id}]}}}
                        }
                        with open(os.path.join(oc_home,"openclaw.json"),"w") as f:
                            json.dump(oc_cfg,f)
                        emit(json.dumps({"type":"status","content":"LLM proxy configured: "+proxy_base}))
                    else:
                        emit(json.dumps({"type":"status","content":"Warning: CHARM_LLM_PROXY_BASE not set, LLM calls may fail"}))
                    cmd=["openclaw","agent","--local","--agent",agent,"--message",msg,"--json"]
                    try:
                        import re as _re
                        # Capture both stdout and stderr: openclaw --json writes output to stderr
                        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
                        stdout_data,stderr_data=proc.communicate()
                        # Parse the complete --json output and emit a final event
                        if proc.returncode==0:
                            parsed=False
                            # Try stderr first (openclaw --json output), then stdout as fallback
                            for raw in [stderr_data,stdout_data]:
                                clean=_re.sub(r"\x1b\[[0-9;]*[mA-Za-z]","",raw.decode("utf-8","replace"))
                                # Find the start of the JSON object, skipping any log lines before it
                                json_start=clean.find("{")
                                if json_start<0:continue
                                try:
                                    result_json=json.loads(clean[json_start:])
                                    texts=[p.get("text","") for p in result_json.get("payloads",[]) if p.get("text")]
                                    final_text="\n".join(texts).strip()
                                    if final_text:
                                        emit(json.dumps({"type":"final","content":final_text}))
                                    parsed=True
                                    break
                                except Exception:pass
                            if not parsed:
                                emit(json.dumps({"type":"error","content":"Could not parse agent JSON output"}))
                        emit(json.dumps({"type":"internal_run_finished","content":{"exit_code":proc.returncode}}))
                    except BrokenPipeError:pass
                    except Exception as e:
                        emit(json.dumps({"type":"error","content":str(e)}))
            print("[Charm Daemon] Listening on :8000",flush=True)
            HTTPServer(("0.0.0.0",8000),H).serve_forever()
        """).strip()

        bash_script = (
            "#!/bin/bash\nset -e\nmkdir -p /workspace\n"
            "cat > /tmp/cd.py << 'PYEOF'\n"
            + daemon_server_py
            + "\nPYEOF\nexec python3 /tmp/cd.py\n"
        )
        return base64.b64encode(bash_script.encode()).decode()

    async def get_machine_status(self, supabase_client, agent_id: str, user_id: str) -> dict:
        """Get current daemon machine status. Returns machine_id, state, and status."""
        if not self.api_token or not self.app_name or not self.api:
            return {"available": False, "error": "Fly.io not configured"}
        api = self.api

        machine_id, volume_id, db_status = self._load_daemon_record(supabase_client, agent_id, user_id)
        if not machine_id:
            return {"available": True, "exists": False, "status": "not_created"}

        try:
            async with aiohttp.ClientSession() as session:
                state = await api.get_machine_state(session, machine_id)
                return {
                    "available": True,
                    "exists": True,
                    "machine_id": machine_id,
                    "volume_id": volume_id,
                    "state": state,
                    "db_status": db_status,
                }
        except Exception as e:
            logger.error("Error getting machine status: %s", e)
            return {"available": True, "exists": True, "error": str(e)}

    async def control_machine(
        self, supabase_client, agent_id: str, user_id: str, action: str
    ) -> dict:
        """
        Control daemon machine: pause, restart, terminate.
        Returns result dict with success boolean.
        """
        if not self.api_token or not self.app_name or not self.api:
            return {"success": False, "error": "Fly.io not configured"}
        api = self.api

        machine_id, volume_id, db_status = self._load_daemon_record(supabase_client, agent_id, user_id)
        if not machine_id:
            return {"success": False, "error": "Machine not found, run agent first to create daemon"}

        try:
            async with aiohttp.ClientSession() as session:
                if action == "pause":
                    stopped = await api.stop_machine(session, machine_id)
                    if stopped:
                        import asyncio
                        for _ in range(10):
                            await asyncio.sleep(3)
                            state = await api.get_machine_state(session, machine_id)
                            if state == "stopped":
                                break
                    if stopped:
                        supabase_client.table("daemon_machines").update(
                            {"status": "paused", "updated_at": "now()"}
                        ).eq("agent_id", agent_id).eq("user_id", user_id).execute()
                    return {"success": stopped, "action": "paused"}

                elif action == "restart":
                    current_state = await api.get_machine_state(session, machine_id)
                    if current_state == "started":
                        restarted = await api.restart_machine(session, machine_id)
                    else:
                        restarted, _ = await self._bring_machine_to_started(session, machine_id)
                    if restarted:
                        supabase_client.table("daemon_machines").update(
                            {"status": "running", "updated_at": "now()"}
                        ).eq("agent_id", agent_id).eq("user_id", user_id).execute()
                    return {"success": restarted, "action": "restarted"}

                elif action == "terminate":
                    current_state = await api.get_machine_state(session, machine_id)
                    if current_state != "stopped":
                        return {
                            "success": False,
                            "error": f"Machine must be stopped first. Current state: {current_state}",
                            "requires_stop": True
                        }
                    deleted = await api.delete_machine(session, machine_id)
                    if deleted:
                        if volume_id and self.app_name:
                            deleted_vol = await api.delete_volume(session, volume_id)
                            logger.info(f"Volume deletion: {deleted_vol}")
                        # Remove from tracking table
                        supabase_client.table("daemon_machines").delete().eq("agent_id", agent_id).eq("user_id", user_id).execute()
                    return {"success": deleted, "action": "terminated"}

                else:
                    return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            logger.error(f"Error controlling machine ({action}): %s", e)
            return {"success": False, "error": str(e)}

    async def _wait_for_started(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        if not self.api:
            return False
        api = self.api
        last_state: Optional[str] = None
        for _ in range(MACHINE_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(MACHINE_POLL_INTERVAL)
            state = await api.get_machine_state(session, machine_id)
            last_state = state
            logger.info("[Fly.io] Machine %s state: %s", machine_id, state)
            if state == "started":
                return True
            if state in ("destroyed", None):
                logger.error(
                    "[Fly.io] Machine %s entered terminal/unavailable state while waiting to start: %s",
                    machine_id,
                    state,
                )
                return False
        logger.error(
            "[Fly.io] Machine %s did not reach started state within %ds (last_state=%s)",
            machine_id,
            MACHINE_POLL_MAX_ATTEMPTS * MACHINE_POLL_INTERVAL,
            last_state,
        )
        return False

    async def _wait_for_stopped(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        if not self.api:
            return False
        api = self.api
        last_state: Optional[str] = None
        for _ in range(MACHINE_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(MACHINE_POLL_INTERVAL)
            state = await api.get_machine_state(session, machine_id)
            last_state = state
            logger.info("[Fly.io] Machine %s state: %s", machine_id, state)
            if state == "stopped":
                return True
            if state == "suspended":
                return True
            if state in ("destroyed", None):
                logger.error(
                    "[Fly.io] Machine %s entered terminal/unavailable state while waiting to stop: %s",
                    machine_id,
                    state,
                )
                return False
        logger.error(
            "[Fly.io] Machine %s did not reach stopped state within %ds (last_state=%s)",
            machine_id,
            MACHINE_POLL_MAX_ATTEMPTS * MACHINE_POLL_INTERVAL,
            last_state,
        )
        return False

    async def _wait_for_settled(
        self, session: aiohttp.ClientSession, machine_id: str
    ) -> Optional[str]:
        """Wait until the machine leaves replacing/stopping/restarting."""
        if not self.api:
            return None
        api = self.api
        state = await api.get_machine_state(session, machine_id)
        for _ in range(MACHINE_POLL_MAX_ATTEMPTS):
            if state not in MACHINE_TRANSITIONAL_STATES:
                return state
            logger.info("[Fly.io] Machine %s state: %s", machine_id, state)
            await asyncio.sleep(MACHINE_POLL_INTERVAL)
            state = await api.get_machine_state(session, machine_id)
        logger.warning(
            "[Fly.io] Machine %s still transitional after %ds (last_state=%s)",
            machine_id,
            MACHINE_POLL_MAX_ATTEMPTS * MACHINE_POLL_INTERVAL,
            state,
        )
        return state

    async def _bring_machine_to_started(
        self, session: aiohttp.ClientSession, machine_id: str
    ) -> tuple[bool, str]:
        """Start or wait for a machine to reach the started state."""
        if not self.api:
            return False, "Fly.io API client is not configured"

        state = await self.api.get_machine_state(session, machine_id)
        logger.info("[Fly.io] Bringing machine %s to started (current=%s)", machine_id, state)

        if state == "started":
            return True, ""
        if state in (None, "destroyed"):
            return False, f"Machine unavailable (state={state})"
        if state in MACHINE_TRANSITIONAL_STATES:
            state = await self._wait_for_settled(session, machine_id)
            if state in (None, "destroyed"):
                return False, f"Machine unavailable after transition (state={state})"
            if state == "started":
                return True, ""

        if state == "created":
            # Bootstrap updates often land here; flyd auto-starts with restart:always.
            # The /start API rejects created (HTTP 412), so wait or restart instead.
            if await self._wait_for_started(session, machine_id):
                return True, ""
            state = await self.api.get_machine_state(session, machine_id)
            if state == "started":
                return True, ""
            logger.info(
                "[Fly.io] Machine %s still %s after wait; trying restart API",
                machine_id,
                state,
            )
            if await self.api.restart_machine(session, machine_id):
                settled = await self._wait_for_settled(session, machine_id)
                if settled == "started" or await self._wait_for_started(session, machine_id):
                    return True, ""
            return False, "Machine did not reach started state after bootstrap refresh"

        if state in ("stopped", "suspended"):
            if not await self.api.start_machine(session, machine_id):
                return False, "Failed to start machine after bootstrap refresh"
            if await self._wait_for_started(session, machine_id):
                return True, ""
            return False, "Machine did not reach started state after bootstrap refresh"

        logger.warning(
            "[Fly.io] Machine %s unexpected state %s; attempting restart",
            machine_id,
            state,
        )
        if await self.api.restart_machine(session, machine_id):
            await self._wait_for_settled(session, machine_id)
            if await self._wait_for_started(session, machine_id):
                return True, ""
        return False, f"Failed to start machine from state {state}"

    async def _restart_machine_after_config_update(
        self, session: aiohttp.ClientSession, machine_id: str
    ) -> tuple[bool, str]:
        """Apply a bootstrap config update by restarting the machine safely."""
        if not self.api:
            return False, "Fly.io API client is not configured"

        state = await self.api.get_machine_state(session, machine_id)
        logger.info("[Fly.io] Machine %s state after bootstrap update: %s", machine_id, state)

        if state == "started":
            # Bootstrap was updated while running — restart to apply.
            if not await self.api.restart_machine(session, machine_id):
                if not await self.api.stop_machine(session, machine_id):
                    return False, "Failed to stop machine before bootstrap refresh"
                if not await self._wait_for_stopped(session, machine_id):
                    settled = await self._wait_for_settled(session, machine_id)
                    if settled not in ("stopped", "suspended", "created", "started"):
                        return False, "Machine did not stop before bootstrap refresh"

        settled = await self._wait_for_settled(session, machine_id)
        if settled in (None, "destroyed"):
            return False, f"Machine unavailable after bootstrap update (state={settled})"

        started, start_err = await self._bring_machine_to_started(session, machine_id)
        if not started:
            return False, start_err

        if not await self._wait_for_started(session, machine_id):
            return False, "Machine did not reach started state after bootstrap refresh"

        return True, ""

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        if not self.api_token or not self.app_name or not self.api:
            yield sse_pack("error", "Fly.io is not configured. Set FLY_API_TOKEN and FLY_APP_NAME.")
            return

        user_id = config.env_vars.get("CHARM_USER_ID", "local")
        yield sse_pack("status", "Checking daemon agent status...")

        machine_id: Optional[str] = None
        volume_id: Optional[str] = None
        machine_just_provisioned = False

        if config.supabase_client:
            user_id = config.env_vars.get("CHARM_USER_ID", "local")
            machine_id, volume_id, _ = self._load_daemon_record(config.supabase_client, config.agent_id, user_id)
            logger.info("[Fly.io] Loaded daemon record: machine=%s volume=%s", machine_id, volume_id)

        async with aiohttp.ClientSession() as session:
            if machine_id:
                state = await self.api.get_machine_state(session, machine_id)
                logger.info("[Fly.io] Existing machine %s is in state: %s", machine_id, state)

                if state == "started":
                    yield sse_pack("status", "Daemon agent is already running.")
                elif state in ("stopped", "suspended", "created"):
                    yield sse_pack("status", "Resuming daemon agent...")
                    started, start_err = await self._bring_machine_to_started(session, machine_id)
                    if not started:
                        yield sse_pack("error", f"Failed to start daemon machine: {start_err}")
                        return
                    yield sse_pack("status", "Waiting for daemon machine to boot...")
                elif state in ("stopping", "restarting", "replacing"):
                    # Machine is mid-transition (e.g. just finished an upgrade run).
                    # Wait for it to settle rather than treating it as gone and
                    # trying to create a new machine — which would fail with AlreadyExists.
                    yield sse_pack("status", "Waiting for daemon machine to finish transitioning...")
                    logger.info("[Fly.io] Machine %s is %s — waiting for it to settle.", machine_id, state)
                    await self._wait_for_settled(session, machine_id)
                    started, start_err = await self._bring_machine_to_started(session, machine_id)
                    if not started:
                        yield sse_pack("error", f"Daemon machine did not reach started state in time: {start_err}")
                        return
                else:
                    # Machine is truly gone (destroyed/unknown) — clear and re-provision
                    logger.warning("[Fly.io] Machine %s is %s, re-provisioning.", machine_id, state)
                    machine_id = None

            if not machine_id:
                if not volume_id:
                    yield sse_pack("status", "Allocating persistent storage volume...")
                    volume_id, vol_err = await self.api.create_volume(session, config.agent_id, user_id)
                    if not volume_id:
                        yield sse_pack("error", f"Failed to allocate storage volume. {vol_err or ''}".strip())
                        return
                    logger.info("[Fly.io] Created volume: %s", volume_id)

                yield sse_pack("status", "Provisioning 24/7 daemon VM...")
                machine_id = await self.api.create_machine(session, config, volume_id, self._generate_bootstrap_script())
                if not machine_id:
                    yield sse_pack("error", "Failed to provision daemon machine.")
                    return

                if config.supabase_client:
                    user_id = config.env_vars.get("CHARM_USER_ID", "local")
                    self._save_daemon_record(config.supabase_client, config.agent_id, user_id, machine_id, volume_id)

                yield sse_pack("status", "Waiting for daemon machine to boot...")
                if not await self._wait_for_started(session, machine_id):
                    yield sse_pack("error", "Daemon machine did not reach started state in time.")
                    return
                machine_just_provisioned = True

            # Wait for the in-machine HTTP server to be healthy
            yield sse_pack("status", "Waiting for agent HTTP server to become ready...")
            if not await self._wait_for_health(session, machine_id):
                yield sse_pack("error", "Daemon agent HTTP server did not become ready in time.")
                return

            needs_handler_refresh = bool(
                config.env_vars.get("CHARM_ROLLBACK_SNAPSHOT_PATH")
                or config.env_vars.get("CHARM_UPGRADE_SNAPSHOT_VERSION")
            )
            skip_refresh_for_fresh_upgrade = bool(
                machine_just_provisioned
                and config.env_vars.get("CHARM_UPGRADE_SNAPSHOT_VERSION")
                and not config.env_vars.get("CHARM_ROLLBACK_SNAPSHOT_PATH")
            )
            if skip_refresh_for_fresh_upgrade:
                logger.info(
                    "[Fly.io] Skipping bootstrap refresh for newly provisioned machine %s (upgrade snapshot via /job env)",
                    machine_id,
                )
            if needs_handler_refresh and not skip_refresh_for_fresh_upgrade:
                if config.env_vars.get("CHARM_ROLLBACK_SNAPSHOT_PATH"):
                    yield sse_pack("status", "Restoring workspace on daemon...")
                elif config.env_vars.get("CHARM_UPGRADE_SNAPSHOT_VERSION"):
                    yield sse_pack("status", "Preparing daemon for upgrade snapshot...")
                yield sse_pack("status", "Updating daemon handler...")
                refreshed, refresh_err = await self._refresh_daemon_bootstrap(session, machine_id, config)
                if not refreshed:
                    logger.error(
                        "[Fly.io] Daemon bootstrap refresh failed for %s: %s",
                        machine_id,
                        refresh_err,
                    )
                    yield sse_pack("error", f"Failed to refresh daemon handler: {refresh_err}")
                    return

            # Dispatch the job and stream results back
            if config.env_vars.get("CHARM_ROLLBACK_SNAPSHOT_PATH"):
                logger.info("[Fly.io] Dispatching rollback restore job to machine %s", machine_id)
                async for event in self._dispatch_job(session, machine_id, config):
                    yield event
                return

            yield sse_pack("status", "Running agent job on daemon...")
            async for event in self._dispatch_job(session, machine_id, config):
                yield event

    async def _refresh_daemon_bootstrap(
        self, session: aiohttp.ClientSession, machine_id: str, config: RunConfig
    ) -> tuple[bool, str]:
        if not self.api:
            return False, "Fly.io API client is not configured"

        bootstrap = self._generate_bootstrap_script()
        # Only refresh bootstrap env keys — merging full rollback env can exceed Fly limits.
        env_overrides: dict[str, str] = {}
        daemon_secret = os.getenv("RUNNER_DAEMON_SECRET", "").strip()
        if daemon_secret:
            env_overrides["RUNNER_DAEMON_SECRET"] = daemon_secret

        updated = await self.api.update_machine_bootstrap(
            session,
            machine_id,
            env_overrides,
            bootstrap,
        )
        if not updated:
            return False, "Failed to update machine bootstrap config"

        restarted, restart_err = await self._restart_machine_after_config_update(session, machine_id)
        if not restarted:
            return False, restart_err

        if not await self._wait_for_health(session, machine_id):
            return False, "Daemon HTTP server did not become healthy after bootstrap refresh"

        return True, ""

    async def _dispatch_restore(
        self, session: aiohttp.ClientSession, machine_id: str, config: RunConfig
    ) -> AsyncGenerator[str, None]:
        """Stream SSE from POST /restore on the daemon machine."""
        url = f"https://{self.app_name}.fly.dev/restore"
        secret = os.getenv("RUNNER_DAEMON_SECRET", "")
        headers = {
            "Content-Type": "application/json",
            "fly-force-instance-id": machine_id,
        }
        if secret:
            headers["X-Daemon-Secret"] = secret

        payload = {
            "workspace": config.env_vars.get("CHARM_WORKSPACE_DIR", "/workspace/agent_code"),
            "snapshot_path": config.env_vars.get("CHARM_ROLLBACK_SNAPSHOT_PATH", ""),
        }
        job_timeout = aiohttp.ClientTimeout(total=config.timeout_seconds or 120)

        async def _stream_restore_events(resp: aiohttp.ClientResponse) -> AsyncGenerator[str, None]:
            buf = ""
            async for chunk in resp.content.iter_any():
                buf += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buf:
                    event_block, buf = buf.split("\n\n", 1)
                    event_block = event_block.strip()
                    if event_block.startswith("data: "):
                        yield event_block + "\n\n"

        async with session.post(url, headers=headers, json=payload, timeout=job_timeout) as resp:
            if resp.status == 404:
                yield sse_pack("status", "Updating daemon restore support...")
                refreshed, refresh_err = await self._refresh_daemon_bootstrap(session, machine_id, config)
                if not refreshed:
                    logger.error(
                        "[Fly.io] Daemon bootstrap refresh failed for %s: %s",
                        machine_id,
                        refresh_err,
                    )
                    yield sse_pack("error", f"Failed to refresh daemon for workspace restore: {refresh_err}")
                    return
                async with session.post(url, headers=headers, json=payload, timeout=job_timeout) as retry_resp:
                    if retry_resp.status != 200:
                        text = await retry_resp.text()
                        yield sse_pack("error", f"Daemon restore dispatch failed ({retry_resp.status}): {text[:200]}")
                        return
                    async for event in _stream_restore_events(retry_resp):
                        yield event
                return

            if resp.status != 200:
                text = await resp.text()
                yield sse_pack("error", f"Daemon restore dispatch failed ({resp.status}): {text[:200]}")
                return

            async for event in _stream_restore_events(resp):
                yield event

    async def _wait_for_health(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        """Poll the machine's /health endpoint until it returns 200 or we time out."""
        url = f"https://{self.app_name}.fly.dev/health"
        headers = {"fly-force-instance-id": machine_id}
        timeout = aiohttp.ClientTimeout(total=5)
        last_error: Optional[str] = None
        last_status: Optional[int] = None
        for attempt in range(MACHINE_HEALTH_MAX_ATTEMPTS):
            await asyncio.sleep(MACHINE_HEALTH_POLL_INTERVAL)
            try:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    last_status = resp.status
                    if resp.status == 200:
                        logger.info("[Fly.io] Machine %s health OK on attempt %d", machine_id, attempt + 1)
                        return True
                    last_error = (await resp.text())[:200]
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "[Fly.io] Health poll attempt %d for %s (%s): %s",
                    attempt + 1,
                    machine_id,
                    url,
                    exc,
                )
        logger.error(
            "[Fly.io] Machine %s health timed out after %ds (url=%s, last_status=%s, last_error=%s). "
            "Confirm Fly app exists (`fly apps list`), machines are running (`fly machine list -a %s`), "
            "and the runtime image starts the daemon HTTP server on port %d.",
            machine_id,
            MACHINE_HEALTH_MAX_ATTEMPTS * MACHINE_HEALTH_POLL_INTERVAL,
            url,
            last_status,
            last_error,
            self.app_name,
            DAEMON_AGENT_PORT,
        )
        return False

    async def _dispatch_job(
        self, session: aiohttp.ClientSession, machine_id: str, config: RunConfig
    ) -> AsyncGenerator[str, None]:
        """POST the job to the daemon agent server and yield SSE events back."""
        url = f"https://{self.app_name}.fly.dev/job"
        secret = os.getenv("RUNNER_DAEMON_SECRET", "")
        headers = {
            "Content-Type": "application/json",
            "fly-force-instance-id": machine_id,
        }
        if secret:
            headers["X-Daemon-Secret"] = secret

        # Extract the user message from the input payload.
        # Agents may use different keys ("message", "input", "task", etc.) depending
        # on how their charm.yaml interface is defined.  Mirror the same key-priority
        # logic used by openclaw.py's invoke() method so the daemon always gets a
        # non-empty message regardless of which key the UI sends.
        _SKIP_KEYS = {"__charm_thread_id__", "__charm_state__"}
        message = (
            config.input_payload.get("message")
            or config.input_payload.get("input", "")
        )
        for _k, _v in config.input_payload.items():
            if _k not in _SKIP_KEYS and _k not in ("message", "input") and isinstance(_v, str) and _v:
                message += f"\n\n[{_k}]: {_v}"
        message = message.strip()

        workspace = config.env_vars.get("CHARM_WORKSPACE_DIR", "/workspace/agent_code")
        bundle_url = config.env_vars.get("CHARM_BUNDLE_SUPABASE_URL", "")

        # Forward essential env vars (API keys + Charm config) to the machine process
        forward_env = {
            k: v
            for k, v in config.env_vars.items()
            if k.startswith("ANTHROPIC_")
            or k.startswith("OPENAI_")
            or k.startswith("CHARM_")
            or k.startswith("NANGO_")
        }

        payload = {
            "message": message,
            "workspace": workspace,
            "agent": "main",
            "bundle_url": bundle_url,
            "env": forward_env,
        }

        job_timeout = aiohttp.ClientTimeout(
            total=config.timeout_seconds or 3600,
            connect=30,
            sock_connect=30,
        )
        try:
            logger.info("[Fly.io] POST %s machine=%s rollback=%s", url, machine_id, bool(forward_env.get("CHARM_ROLLBACK_SNAPSHOT_PATH")))
            async with session.post(
                url, headers=headers, json=payload, timeout=job_timeout
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    yield sse_pack("error", f"Daemon job dispatch failed ({resp.status}): {text}")
                    return

                # Stream SSE events, buffering across chunk boundaries
                buf = ""
                async for chunk in resp.content.iter_any():
                    buf += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in buf:
                        event_block, buf = buf.split("\n\n", 1)
                        event_block = event_block.strip()
                        if event_block.startswith("data: "):
                            yield event_block + "\n\n"

        except asyncio.TimeoutError:
            yield sse_pack("error", "Daemon agent job timed out.")
        except Exception as exc:
            logger.error("[Fly.io] Job dispatch error for machine %s: %s", machine_id, exc)
            yield sse_pack("error", f"Daemon dispatch error: {exc}")

    async def cleanup(self, run_id: str):
        pass
