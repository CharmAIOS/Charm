from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional
from pydantic import BaseModel


class RunConfig(BaseModel):
    """
    標準化的執行配置，無論是 Docker 還是 Cloud Run 都需要這些資訊。
    """

    agent_id: str
    run_id: str
    bundle_url: str
    input_payload: Dict[str, Any]
    env_vars: Dict[str, str]
    file_urls: Dict[str, str]
    script_content: str  # 已生成的 Bash 啟動腳本

    # 資源路徑 (主要用於 Local Docker 掛載，Cloud Run 會忽略或用不同方式處理)
    host_artifact_path: str
    host_cache_dir: str
    local_source_path: Optional[str] = None


class ExecutionBackend(ABC):
    """
    執行後端介面。
    未來新增 CloudRunBackend 時，只需實作這個 Class。
    """

    @abstractmethod
    async def stream_logs(self, config: RunConfig) -> AsyncGenerator[str, None]:
        """
        啟動任務並回傳 SSE 格式的日誌流 (yield "data: ...")
        """
        pass

    @abstractmethod
    async def cleanup(self, run_id: str):
        """
        清理資源 (如刪除容器、刪除臨時 Job)
        """
        pass
