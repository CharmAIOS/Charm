import json
from typing import Any

# String to identify system events in stdout
EVENT_PREFIX = "__CHARM_EVENT__"


def sse_pack(event_type: str, content: Any = "") -> str:
    """
    Formats a payload into a Server-Sent Events (SSE) data string.

    Args:
        event_type: The type of event (e.g., 'status', 'thinking', 'delta').
        content: The payload data (string or dict).

    Returns:
        A formatted SSE string starting with 'data: '.
    """
    payload = {"type": event_type, "content": content}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
