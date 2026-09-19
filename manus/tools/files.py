"""File tools confined to the workspace. Traversal and symlink escapes are refused."""

from __future__ import annotations

from pathlib import Path

from manus.tools.base import Tool, ToolContext
from manus.util import truncate_bytes


def resolve_confined(workspace: Path, raw: str) -> Path:
    """Resolve `raw` against the workspace and refuse anything that escapes it.

    resolve() follows symlinks, so a link pointing outside the workspace is caught
    by the same is_relative_to check as plain .. traversal.
    """
    root = workspace.resolve()
    raw_path = Path(raw).expanduser()
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    resolved = candidate.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(
            f"path {raw!r} escapes the workspace ({root}); file tools only operate inside it"
        )
    return resolved


class FileReadTool(Tool):
    name = "file_read"
    description = "Read a file in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."}
        },
        "required": ["path"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        try:
            path = resolve_confined(ctx.workspace, str(args.get("path", "")))
            content = path.read_text(encoding="utf-8", errors="replace")
            if not content:
                return "(empty file)"
            return truncate_bytes(content, ctx.config.observe_cap_bytes)
        except Exception as exc:
            return f"Error: {exc}"


class FileWriteTool(Tool):
    name = "file_write"
    description = "Write a file in the workspace (creates parent directories)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."},
            "content": {"type": "string", "description": "Full file content to write."},
        },
        "required": ["path", "content"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        try:
            path = resolve_confined(ctx.workspace, str(args.get("path", "")))
            content = str(args.get("content", ""))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content.encode('utf-8'))} bytes to {path.name}"
        except Exception as exc:
            return f"Error: {exc}"


class FileListTool(Tool):
    name = "file_list"
    description = "List a directory in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory relative to the workspace root; default is the root.",
            }
        },
        "required": [],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        try:
            raw = str(args.get("path", "") or "")
            directory = resolve_confined(ctx.workspace, raw)
            if not directory.is_dir():
                return f"Error: {raw or '.'} is not a directory"
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = [f"{p.name}/" if p.is_dir() else p.name for p in entries]
            if not lines:
                return "(empty directory)"
            return truncate_bytes("\n".join(lines), ctx.config.observe_cap_bytes)
        except Exception as exc:
            return f"Error: {exc}"
