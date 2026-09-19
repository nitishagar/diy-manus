"""Builtin tools: finish (loop termination) and recall (search past sessions)."""

from __future__ import annotations

from manus.tools.base import Tool, ToolContext


class FinishTool(Tool):
    name = "finish"
    description = (
        "End the task with a final summary for the user. Call this once the goal "
        "is achieved (or cannot be progressed further), never mid-task."
    )
    parameters = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Concise final summary of what was done and the result.",
            }
        },
        "required": ["summary"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        return str(args.get("summary", "")).strip()


class RecallTool(Tool):
    name = "recall"
    description = (
        "Search the memory of past task runs on this machine. Use to reuse earlier "
        "results, commands, or findings relevant to the current task."
    )
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Full-text search query."}},
        "required": ["query"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "Error: recall needs a non-empty query."
        if ctx.session is None:
            return "No history available."
        return ctx.session.search_text(query)
