import asyncio
import base64
import os
import aiohttp
import logging
import textwrap
from typing import AsyncGenerator, Optional, Tuple
from .base import ExecutionBackend, RunConfig
from ...runner.protocol import sse_pack

logger = logging.getLogger("charm.runner.fly_io")

FLY_API_BASE = "https://api.machines.dev/v1"
MACHINE_POLL_INTERVAL = 2
MACHINE_POLL_MAX_ATTEMPTS = 15
MACHINE_HEALTH_POLL_INTERVAL = 3
MACHINE_HEALTH_MAX_ATTEMPTS = 20
DAEMON_AGENT_PORT = 8000


class FlyIoBackend(ExecutionBackend):

    def __init__(self):
        self.api_token = os.getenv("FLY_API_TOKEN")
        self.app_name = os.getenv("FLY_APP_NAME")
        self.region = os.getenv("FLY_REGION", "sjc")

        if not self.app_name:
            logger.warning("FLY_APP_NAME is not set. Daemon mode will fail.")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    def _load_daemon_record(self, supabase_client, agent_id: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            result = (
                supabase_client.table("daemon_machines")
                .select("fly_machine_id,fly_volume_id")
                .eq("agent_id", agent_id)
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data.get("fly_machine_id"), result.data.get("fly_volume_id")
        except Exception as e:
            logger.warning("Failed to load daemon record: %s", e)
        return None, None

    def _save_daemon_record(self, supabase_client, agent_id: str, machine_id: str, volume_id: Optional[str]):
        try:
            supabase_client.table("daemon_machines").upsert(
                {
                    "agent_id": agent_id,
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
                    env={**os.environ,**xenv}
                    cmd=["openclaw","agent","--local","--agent",agent,"--workspace",ws,"--message",msg,"--json"]
                    try:
                        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
                        for line in proc.stdout:
                            emit(line.decode("utf-8","replace").rstrip())
                        proc.wait()
                        emit(json.dumps({"type":"internal_run_finished","exit_code":proc.returncode}))
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

    async def _get_machine_state(self, session: aiohttp.ClientSession, machine_id: str) -> Optional[str]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}"
        try:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status == 404:
                    return "destroyed"
                data = await resp.json()
                return data.get("state")
        except Exception as e:
            logger.error("Error fetching machine state for %s: %s", machine_id, e)
            return None

    async def _start_machine(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}/start"
        async with session.post(url, headers=self._headers()) as resp:
            return resp.status in (200, 201)

    async def _wait_for_started(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        for _ in range(MACHINE_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(MACHINE_POLL_INTERVAL)
            state = await self._get_machine_state(session, machine_id)
            logger.info("[Fly.io] Machine %s state: %s", machine_id, state)
            if state == "started":
                return True
            if state in ("destroyed", None):
                return False
        return False

    async def _create_volume(self, session: aiohttp.ClientSession, agent_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Returns (volume_id, error_message). One of the two will be None."""
        url = f"{FLY_API_BASE}/apps/{self.app_name}/volumes"
        vol_name = f"charm_{agent_id.replace('-', '')[:20]}"
        payload = {"name": vol_name, "region": self.region, "size_gb": 1}
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("[Fly.io] Volume creation failed (HTTP %s): %s", resp.status, text)
                return None, f"HTTP {resp.status}: {text}"
            data = await resp.json()
            return data.get("id"), None

    async def _create_machine(
        self, session: aiohttp.ClientSession, config: RunConfig, volume_id: Optional[str]
    ) -> Optional[str]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines"
        machine_name = f"charm-{config.agent_id[:8]}"
        mounts = [{"volume": volume_id, "path": "/workspace"}] if volume_id else []
        payload = {
            "name": machine_name,
            "region": self.region,
            "config": {
                "image": config.image or "ucmind/runner-base:latest",
                "env": {
                        **config.env_vars,
                        "CHARM_DAEMON_MODE": "true",
                        "CHARM_BOOTSTRAP_SCRIPT": self._generate_bootstrap_script(),
                    },
                "init": {
                    "cmd": ["/bin/bash", "-c", "echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash"]
                },
                "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 1024},
                "mounts": mounts,
                "services": [
                    {
                        "protocol": "tcp",
                        "internal_port": 8000,
                        "ports": [
                            {"port": 80, "handlers": ["http"]},
                            {"port": 443, "handlers": ["tls", "http"]},
                        ],
                    }
                ],
                "restart": {"policy": "always"},
            },
        }
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("[Fly.io] Machine creation failed: %s", text)
                return None
            data = await resp.json()
            machine_id = data.get("id")
            logger.info("[Fly.io] Created machine %s (%s)", machine_id, machine_name)
            return machine_id

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        if not self.api_token or not self.app_name:
            yield sse_pack("error", "Fly.io is not configured. Set FLY_API_TOKEN and FLY_APP_NAME.")
            return

        yield sse_pack("status", "Checking daemon agent status...")

        machine_id: Optional[str] = None
        volume_id: Optional[str] = None

        if config.supabase_client:
            machine_id, volume_id = self._load_daemon_record(config.supabase_client, config.agent_id)
            logger.info("[Fly.io] Loaded daemon record: machine=%s volume=%s", machine_id, volume_id)

        async with aiohttp.ClientSession() as session:
            if machine_id:
                state = await self._get_machine_state(session, machine_id)
                logger.info("[Fly.io] Existing machine %s is in state: %s", machine_id, state)

                if state == "started":
                    yield sse_pack("status", "Daemon agent is already running.")
                elif state in ("stopped", "suspended", "created"):
                    yield sse_pack("status", "Resuming daemon agent...")
                    started = await self._start_machine(session, machine_id)
                    if not started:
                        yield sse_pack("error", "Failed to start daemon machine.")
                        return
                    yield sse_pack("status", "Waiting for daemon machine to boot...")
                    if not await self._wait_for_started(session, machine_id):
                        yield sse_pack("error", "Daemon machine did not reach started state in time.")
                        return
                else:
                    # Machine is gone — clear it and re-provision below
                    logger.warning("[Fly.io] Machine %s is %s, re-provisioning.", machine_id, state)
                    machine_id = None

            if not machine_id:
                if not volume_id:
                    yield sse_pack("status", "Allocating persistent storage volume...")
                    volume_id, vol_err = await self._create_volume(session, config.agent_id)
                    if not volume_id:
                        yield sse_pack("error", f"Failed to allocate storage volume. {vol_err or ''}".strip())
                        return
                    logger.info("[Fly.io] Created volume: %s", volume_id)

                yield sse_pack("status", "Provisioning 24/7 daemon VM...")
                machine_id = await self._create_machine(session, config, volume_id)
                if not machine_id:
                    yield sse_pack("error", "Failed to provision daemon machine.")
                    return

                if config.supabase_client:
                    self._save_daemon_record(config.supabase_client, config.agent_id, machine_id, volume_id)

                yield sse_pack("status", "Waiting for daemon machine to boot...")
                if not await self._wait_for_started(session, machine_id):
                    yield sse_pack("error", "Daemon machine did not reach started state in time.")
                    return

            # Wait for the in-machine HTTP server to be healthy
            yield sse_pack("status", "Waiting for agent HTTP server to become ready...")
            if not await self._wait_for_health(session, machine_id):
                yield sse_pack("error", "Daemon agent HTTP server did not become ready in time.")
                return

            # Dispatch the job and stream results back
            yield sse_pack("status", "Running agent job on daemon...")
            async for event in self._dispatch_job(session, machine_id, config):
                yield event

    async def _wait_for_health(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        """Poll the machine's /health endpoint until it returns 200 or we time out."""
        url = f"https://{self.app_name}.fly.dev/health"
        headers = {"fly-force-instance-id": machine_id}
        timeout = aiohttp.ClientTimeout(total=5)
        for attempt in range(MACHINE_HEALTH_MAX_ATTEMPTS):
            await asyncio.sleep(MACHINE_HEALTH_POLL_INTERVAL)
            try:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    if resp.status == 200:
                        logger.info("[Fly.io] Machine %s health OK on attempt %d", machine_id, attempt + 1)
                        return True
            except Exception as exc:
                logger.debug("[Fly.io] Health poll attempt %d for %s: %s", attempt + 1, machine_id, exc)
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

        message = config.input_payload.get("message", "")
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

        job_timeout = aiohttp.ClientTimeout(total=config.timeout_seconds or 3600)
        try:
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
