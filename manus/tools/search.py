"""Web search: keyless ddgs by default, optional local SearXNG backend."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from manus.tools.base import Tool, ToolContext
from manus.util import truncate_bytes


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web and return titles, URLs and snippets. Requires no API key "
        "(local DuckDuckGo backend by default, or a self-hosted SearXNG)."
    )
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query."}},
        "required": ["query"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "Error: web_search needs a non-empty query."
        try:
            if ctx.config.search_backend == "searxng":
                results = self._searxng(query, ctx)
            else:
                results = self._ddgs(query, ctx)
        except Exception as exc:
            return f"Search error: {type(exc).__name__}: {exc}"
        if not results:
            return "No results found."
        lines = [
            f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results, 1)
        ]
        return truncate_bytes("\n".join(lines), ctx.config.observe_cap_bytes)

    @staticmethod
    def _ddgs(query: str, ctx: ToolContext) -> list[dict]:
        from ddgs import DDGS  # lazy: optional dependency, never imported at module load

        raw = DDGS(timeout=ctx.config.net_timeout_s).text(
            query, max_results=ctx.config.search_cap_results
        )
        return [
            {
                "title": str(r.get("title", ""))[:200],
                "url": str(r.get("href", ""))[:500],
                "snippet": str(r.get("body", ""))[:300],
            }
            for r in raw
        ]

    @staticmethod
    def _searxng(query: str, ctx: ToolContext) -> list[dict]:
        base = ctx.config.searxng_url.rstrip("/")
        url = f"{base}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
        request = urllib.request.Request(url, headers={"User-Agent": "diy-manus/0.1"})
        with urllib.request.urlopen(request, timeout=ctx.config.net_timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            {
                "title": str(r.get("title", ""))[:200],
                "url": str(r.get("url", ""))[:500],
                "snippet": str(r.get("content", ""))[:300],
            }
            for r in payload.get("results", [])[: ctx.config.search_cap_results]
        ]
