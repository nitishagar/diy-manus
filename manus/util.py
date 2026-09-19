"""Small shared helpers: observation capping and tool-call recovery from prose."""

from __future__ import annotations

import json
from typing import Optional

from manus.llm import ToolCall

TRUNCATION_MARKER = "…[truncated]"


def truncate_bytes(text: str, cap: int) -> str:
    """Cap text to at most `cap` bytes, appending a visible marker when cut.

    Caps on character boundaries so multi-byte unicode is never split mid-codepoint.
    """
    if cap <= 0 or len(text.encode("utf-8")) <= cap:
        return text
    cut = cap - len(TRUNCATION_MARKER.encode("utf-8"))
    encoded = text.encode("utf-8")[:cut].decode("utf-8", errors="ignore")
    return encoded + TRUNCATION_MARKER


def extract_tool_call_from_prose(content: str) -> Optional[ToolCall]:
    """Recover a tool call from prose that wraps a JSON object.

    Small local models sometimes answer with plain text containing a single JSON
    object like {"name": "file_write", "arguments": {...}}. Scans the first
    balanced {...} block that parses and carries a "name" key.
    """
    if not content or "{" not in content:
        return None
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(content):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = content[start : i + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(parsed, dict) and "name" in parsed:
                    arguments = parsed.get("arguments", parsed.get("args", {}))
                    if not isinstance(arguments, dict):
                        arguments = {}
                    return ToolCall(
                        name=str(parsed["name"]),
                        arguments=json.dumps(arguments, ensure_ascii=False),
                    )
                start = -1
    return None
