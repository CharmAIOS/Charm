import re
from collections import deque
from typing import Optional


def clean_log_fallback(line: str) -> Optional[str]:
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    clean_line = ansi_escape.sub("", line)
    clean_line = re.sub(r"[\u2500-\u257f]", "", clean_line)
    if "type: ignore" in clean_line or "site-packages" in clean_line:
        return None

    return clean_line.strip()


def is_duplicate_log(line: str, recent_events: deque) -> bool:
    clean = line.strip()
    if not clean:
        return False

    for event_content in recent_events:
        if clean in event_content or event_content in clean:
            return True
    return False
