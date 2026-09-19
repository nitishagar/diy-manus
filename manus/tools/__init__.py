"""Tool package: fixed registry assembly. The list never mutates mid-run."""

from __future__ import annotations

from manus.tools.base import Tool, ToolContext, ToolRegistry
from manus.tools.builtin import FinishTool, RecallTool
from manus.tools.browser import BrowserClickTool, BrowserNavigateTool, BrowserSnapshotTool
from manus.tools.fetch import WebFetchTool
from manus.tools.files import FileListTool, FileReadTool, FileWriteTool
from manus.tools.search import WebSearchTool
from manus.tools.shell import ShellExecTool

__all__ = [
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "FinishTool",
    "RecallTool",
    "default_registry",
]


def default_registry() -> ToolRegistry:
    """The agent's complete, fixed tool set."""
    return ToolRegistry(
        tools=[
            FinishTool(),
            RecallTool(),
            FileReadTool(),
            FileWriteTool(),
            FileListTool(),
            ShellExecTool(),
            WebSearchTool(),
            WebFetchTool(),
            BrowserNavigateTool(),
            BrowserSnapshotTool(),
            BrowserClickTool(),
        ]
    )
