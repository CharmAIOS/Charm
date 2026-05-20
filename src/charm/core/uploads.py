"""Helpers for reading user-uploaded files injected by the interactive worker."""

from __future__ import annotations

import os
from typing import Dict, Mapping, MutableMapping

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".py",
    ".html",
    ".htm",
    ".xml",
    ".log",
    ".rst",
    ".ini",
    ".cfg",
    ".env",
}

DEFAULT_MAX_FILE_CHARS = 80_000
DEFAULT_MAX_TOTAL_CHARS = 120_000


def read_uploaded_file_text(path: str, *, max_chars: int = DEFAULT_MAX_FILE_CHARS) -> str:
    """Read text from an uploaded file path, with a safe size cap."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return f"[Uploaded file '{os.path.basename(path)}' ({ext or 'no extension'}) is not a supported text type.]"

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read(max_chars + 1)
    except OSError as exc:
        return f"[Could not read uploaded file '{os.path.basename(path)}': {exc}]"

    if len(content) > max_chars:
        return content[:max_chars] + "\n\n[... truncated ...]"
    return content


def build_upload_context(
    file_map: Mapping[str, str],
    *,
    max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """Build a prompt block from downloaded upload paths."""
    if not file_map:
        return ""

    sections: list[str] = []
    total_chars = 0
    for display_name, path in file_map.items():
        if not path or not os.path.isfile(path):
            sections.append(f"### {display_name}\n[Upload missing on disk.]")
            continue

        remaining = max_total_chars - total_chars
        if remaining <= 0:
            sections.append(f"### {display_name}\n[Skipped: upload context limit reached.]")
            continue

        per_file_limit = min(max_file_chars, remaining)
        body = read_uploaded_file_text(path, max_chars=per_file_limit)
        section = f"### {display_name}\n{body}"
        sections.append(section)
        total_chars += len(section)

    return "\n\n".join(sections)


def inject_uploads_into_inputs(
    payload: MutableMapping[str, object],
    file_map: Mapping[str, str],
    *,
    max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> None:
    """Merge uploaded file text into common message fields on the invoke payload."""
    context = build_upload_context(
        file_map,
        max_file_chars=max_file_chars,
        max_total_chars=max_total_chars,
    )
    if not context:
        return

    message_key = next(
        (key for key in ("message", "input", "task") if key in payload),
        "message",
    )
    existing = str(payload.get(message_key) or "").strip()
    attachment_block = (
        "The user uploaded the following file(s). Use their contents to answer:\n\n" + context
    )
    payload[message_key] = f"{existing}\n\n{attachment_block}".strip() if existing else attachment_block
