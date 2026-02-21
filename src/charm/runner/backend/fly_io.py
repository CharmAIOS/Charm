import os
import aiohttp
import logging
from typing import AsyncGenerator
from .base import ExecutionBackend, RunConfig
from ...runner.protocol import sse_pack

logger = logging.getLogger("charm.runner.fly_io")


class FlyIoBackend(ExecutionBackend):
    """
    Production-ready Fly.io backend for 24/7 Daemon Agents.
    Uses the Fly Machines REST API to dynamically provision MicroVMs and Persistent Volumes.
    """

    def __init__(self):
        self.api_token = os.getenv("FLY_API_TOKEN")
        self.app_name = os.getenv("FLY_APP_NAME")

        if not self.app_name:
            logger.warning("FLY_APP_NAME is not set. Daemon mode may fail.")

    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        if not self.api_token or not self.app_name:
            yield sse_pack("error", "Platform Error: Fly.io integration is not fully configured.")
            return

        yield sse_pack("status", f"Provisioning 24/7 Daemon VM on Fly.io (App: {self.app_name})...")

        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            yield sse_pack("status", "Allocating persistent storage volume...")

            vol_payload = {"name": "charm_workspace", "region": "nrt", "size_gb": 1}
            vol_api_url = f"https://api.machines.dev/v1/apps/{self.app_name}/volumes"

            async with session.post(vol_api_url, headers=headers, json=vol_payload) as vol_resp:
                if vol_resp.status not in [200, 201]:
                    error_data = await vol_resp.text()
                    logger.error(f"[Fly.io Volume Error] {error_data}")
                    yield sse_pack("error", f"Failed to allocate volume: {error_data}")
                    return

                vol_data = await vol_resp.json()
                volume_id = vol_data.get("id")
                logger.info(f"Successfully created Fly Volume: {volume_id}")

            yield sse_pack("status", "Booting machine and mounting workspace...")

            machine_api_url = f"https://api.machines.dev/v1/apps/{self.app_name}/machines"
            machine_payload = {
                "name": f"agent-{config.agent_id.lower()[:10]}-{config.run_id[:5]}",
                "region": "nrt",
                "config": {
                    "image": config.image or "python:3.11-slim",
                    "env": config.env_vars,
                    "init": {
                        "cmd": [
                            "/bin/bash",
                            "-c",
                            "echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash",
                        ]
                    },
                    "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 512},
                    "mounts": [{"volume": volume_id, "path": "/workspace"}],
                    # "services": [{
                    #     "protocol": "tcp",
                    #     "internal_port": 8000,
                    #     "ports": [
                    #         {"port": 80, "handlers": ["http"]},
                    #         {"port": 443, "handlers": ["tls", "http"]}
                    #     ]
                    # }]
                },
            }

            async with session.post(machine_api_url, headers=headers, json=machine_payload) as resp:
                if resp.status != 200:
                    error_data = await resp.text()
                    logger.error(f"[Fly.io Machine Error] {error_data}")
                    yield sse_pack("error", f"Failed to provision daemon: {error_data}")
                    return

                machine_data = await resp.json()
                machine_id = machine_data.get("id")
                machine_name = machine_data.get("name")

                logger.info(f"Successfully created Fly Machine: {machine_id} ({machine_name})")

        yield sse_pack("status", "Daemon Agent is now live and running 24/7 in the background.")

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
