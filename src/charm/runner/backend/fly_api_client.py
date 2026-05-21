import logging
from typing import Any, Optional, Tuple

import aiohttp

logger = logging.getLogger("charm.runner.fly_api_client")
FLY_API_BASE = "https://api.machines.dev/v1"

class FlyApiClient:
    def __init__(self, api_token: str, app_name: str, region: str = "sjc"):
        self.api_token = api_token
        self.app_name = app_name
        self.region = region

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    async def get_machine(self, session: aiohttp.ClientSession, machine_id: str) -> Optional[dict[str, Any]]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}"
        try:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("[Fly.io] Failed to fetch machine %s (HTTP %s): %s", machine_id, resp.status, text)
                    return None
                data = await resp.json()
                return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error("Error fetching machine %s: %s", machine_id, e)
            return None

    async def get_machine_state(self, session: aiohttp.ClientSession, machine_id: str) -> Optional[str]:
        machine = await self.get_machine(session, machine_id)
        if machine is None:
            return "destroyed"
        return machine.get("state")

    async def start_machine(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}/start"
        async with session.post(url, headers=self._headers()) as resp:
            return resp.status in (200, 201)

    async def stop_machine(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}/stop"
        async with session.post(url, headers=self._headers()) as resp:
            if resp.status not in (200, 201):
                return False
            # We don't poll here, polling is handled in the backend layer if needed
            return True

    async def delete_machine(self, session: aiohttp.ClientSession, machine_id: str) -> bool:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}"
        async with session.delete(url, headers=self._headers()) as resp:
            return resp.status in (200, 201)

    async def delete_volume(self, session: aiohttp.ClientSession, volume_id: str) -> bool:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/volumes/{volume_id}"
        async with session.delete(url, headers=self._headers()) as resp:
            return resp.status in (200, 201)

    async def update_machine_bootstrap(
        self,
        session: aiohttp.ClientSession,
        machine_id: str,
        env_vars: dict[str, str],
        bootstrap_script: str,
    ) -> bool:
        """Push an updated bootstrap script to an existing machine config."""
        machine = await self.get_machine(session, machine_id)
        if not machine:
            return False

        current_config = machine.get("config")
        if not isinstance(current_config, dict) or not current_config.get("image"):
            logger.error("[Fly.io] Machine %s is missing config.image; cannot update bootstrap", machine_id)
            return False

        merged_env = dict(current_config.get("env") or {})
        merged_env.update(env_vars)
        merged_env["CHARM_DAEMON_MODE"] = "true"
        merged_env["CHARM_BOOTSTRAP_SCRIPT"] = bootstrap_script

        updated_config = dict(current_config)
        updated_config["env"] = merged_env
        updated_config["init"] = {
            "cmd": ["/bin/bash", "-c", "echo $CHARM_BOOTSTRAP_SCRIPT | base64 -d | bash"]
        }

        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines/{machine_id}"
        payload = {"config": updated_config}
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("[Fly.io] Machine bootstrap update failed (HTTP %s): %s", resp.status, text)
                return False
            return True

    async def create_volume(self, session: aiohttp.ClientSession, agent_id: str, user_id: str) -> Tuple[Optional[str], Optional[str]]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/volumes"
        clean_user = user_id.replace('-', '')[:10]
        clean_agent = agent_id.replace('-', '')[:10]
        vol_name = f"c_{clean_user}_{clean_agent}"
        payload = {"name": vol_name, "region": self.region, "size_gb": 1}
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("[Fly.io] Volume creation failed (HTTP %s): %s", resp.status, text)
                return None, f"HTTP {resp.status}: {text}"
            data = await resp.json()
            return data.get("id"), None

    async def create_machine(
        self, session: aiohttp.ClientSession, config: Any, volume_id: Optional[str], bootstrap_script: str
    ) -> Optional[str]:
        url = f"{FLY_API_BASE}/apps/{self.app_name}/machines"
        user_id = config.env_vars.get("CHARM_USER_ID", "local")
        clean_user = user_id.replace('-', '')[:8]
        clean_agent = config.agent_id.replace('-', '')[:8]
        machine_name = f"c-{clean_user}-{clean_agent}"
        mounts = [{"volume": volume_id, "path": "/workspace"}] if volume_id else []
        payload = {
            "name": machine_name,
            "region": self.region,
            "config": {
                "image": config.image or "ucmind/runner-base:latest",
                "env": {
                        **config.env_vars,
                        "CHARM_DAEMON_MODE": "true",
                        "CHARM_BOOTSTRAP_SCRIPT": bootstrap_script,
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
