import asyncio
import os
import aiohttp
import logging
from typing import AsyncGenerator, Optional, Tuple
from .base import ExecutionBackend, RunConfig
from ...runner.protocol import sse_pack

logger = logging.getLogger("charm.runner.fly_io")

FLY_API_BASE = "https://api.machines.dev/v1"
MACHINE_POLL_INTERVAL = 2
MACHINE_POLL_MAX_ATTEMPTS = 15


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

    async def _create_volume(self, session: aiohttp.ClientSession, agent_id: str) -> Optional[str]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/volumes"
        vol_name = f"charm_{agent_id.replace('-', '')[:20]}"
        payload = {"name": vol_name, "region": self.region, "size_gb": 1}
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("[Fly.io] Volume creation failed: %s", text)
                return None
            data = await resp.json()
            return data.get("id")

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
                "env": {**config.env_vars, "CHARM_DAEMON_MODE": "true"},
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
                    yield sse_pack("status", "Waiting for daemon to become ready...")
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
                    volume_id = await self._create_volume(session, config.agent_id)
                    if not volume_id:
                        yield sse_pack("error", "Failed to allocate storage volume.")
                        return
                    logger.info("[Fly.io] Created volume: %s", volume_id)

                yield sse_pack("status", "Provisioning 24/7 daemon VM...")
                machine_id = await self._create_machine(session, config, volume_id)
                if not machine_id:
                    yield sse_pack("error", "Failed to provision daemon machine.")
                    return

                if config.supabase_client:
                    self._save_daemon_record(config.supabase_client, config.agent_id, machine_id, volume_id)

                yield sse_pack("status", "Waiting for daemon to become ready...")
                if not await self._wait_for_started(session, machine_id):
                    yield sse_pack("error", "Daemon machine did not reach started state in time.")
                    return

        yield sse_pack("status", "Daemon agent is live and running 24/7.")
        yield sse_pack(
            "control",
            {
                "status": "daemon_ready",
                "machine_id": machine_id,
                "public_url": f"https://{self.app_name}.fly.dev",
            },
        )

    async def cleanup(self, run_id: str):
        pass
