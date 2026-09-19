"""Tool abstraction and fixed registry. The tool list never mutates mid-run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from manus.config import Config


class SessionLike(Protocol):
    """What a session store must offer to tools (satisfied by manus.session.SessionStore)."""

    def search_text(self, query: str) -> str: ...


@dataclass
class ToolContext:
    """Everything a tool may need: where it acts and how it is bounded."""

    workspace: Path
    config: Config
    session: Optional[SessionLike] = None  # wired by the CLI


class Tool:
    """One capability the agent can invoke, exactly once per iteration."""

    name: str = ""
    description: str = ""
    parameters: Dict = {"type": "object", "properties": {}, "required": []}

    def run(self, args: dict, ctx: ToolContext) -> str:
        raise NotImplementedError


@dataclass
class ToolRegistry:
    tools: List[Tool] = field(default_factory=list)

    def schemas(self) -> List[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self.tools
        ]

    def get(self, name: str) -> Optional[Tool]:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
