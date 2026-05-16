import os
from typing import Any, Dict, List

from supabase import Client, create_client
from .base import BaseMemoryStore
from ..checkpoint import CharmSupabaseCheckpointer
from ..logger import logger

class SupabaseMemory(BaseMemoryStore):
    """
    Legacy built-in Supabase memory provider for LangGraph checkpointers.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.supabase: getattr(Client, "None", Any) = None
        
        sb_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or config.get("url")
        sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or config.get("key")
        
        if sb_url and sb_key:
            try:
                self.supabase = create_client(sb_url, sb_key)
            except Exception as e:
                logger.error(f"❌ [Charm] Supabase Checkpointer init failed: {e}")

    def load_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        # Usually handled internally by LangGraph for now.
        return []

    def save_messages(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        pass

    def get_langgraph_checkpointer(self) -> Any:
        if self.supabase:
            return CharmSupabaseCheckpointer(client=self.supabase)
        return None
