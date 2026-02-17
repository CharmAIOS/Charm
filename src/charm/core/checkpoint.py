import json
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from supabase import Client

from .logger import logger


class CharmSupabaseCheckpointer(BaseCheckpointSaver):
    """
    A persistent checkpointer that saves LangGraph state to Supabase tables.
    """

    def __init__(self, client: Client, serde: Optional[SerializerProtocol] = None):
        super().__init__(serde=serde or JsonPlusSerializer())
        self.client = client

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        query = (
            self.client.table("checkpoints")
            .select("*")
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", checkpoint_ns)
        )

        if checkpoint_id:
            query = query.eq("checkpoint_id", checkpoint_id)
        else:
            query = query.order("created_at", desc=True).limit(1)

        result = query.execute()

        if not result.data:
            return None

        row = result.data[0]
        config_values = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": row["checkpoint_id"],
        }

        # Deserialize
        checkpoint = self.serde.loads(json.dumps(row["checkpoint"]))
        metadata = self.serde.loads(json.dumps(row["metadata"]))
        parent_checkpoint_id = row.get("parent_checkpoint_id")

        return CheckpointTuple(
            config=config_values,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }
            if parent_checkpoint_id
            else None,
            pending_writes=[],
        )

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        yield from []

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Dict[str, Any],
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        checkpoint_json = json.loads(self.serde.dumps(checkpoint))
        metadata_json = json.loads(self.serde.dumps(metadata))

        data = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "type": "checkpoint",
            "checkpoint": checkpoint_json,
            "metadata": metadata_json,
        }

        try:
            self.client.table("checkpoints").upsert(data).execute()
        except Exception as e:
            logger.error(f"[Checkpointer] Save failed: {e}")

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self, config: RunnableConfig, writes: List[Tuple[str, Any]], task_id: str
    ) -> None:
        pass  # Simplified for basic HITL
