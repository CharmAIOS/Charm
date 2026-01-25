from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional

from pydantic import BaseModel


class RunConfig(BaseModel):
    agent_id: str
    run_id: str
    bundle_url: str
    input_payload: Dict[str, Any]
    env_vars: Dict[str, str]
    file_urls: Dict[str, str]
    script_content: str
    host_artifact_path: str
    host_cache_dir: str
    local_source_path: Optional[str] = None


class ExecutionBackend(ABC):
    @abstractmethod
    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def cleanup(self, run_id: str):
        pass
