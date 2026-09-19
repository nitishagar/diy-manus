"""Web page fetch: bounded download + trafilatura main-content extraction."""

from __future__ import annotations

import urllib.request

from manus.tools.base import Tool, ToolContext
from manus.util import truncate_bytes

USER_AGENT = "Mozilla/5.0 (compatible; diy-manus/0.1; local-first agent)"
# HTML shrinks roughly 10x through text extraction, so 10 caps of raw HTML
# are enough to fill one cap of extracted text.
FETCH_MULTIPLE = 10


class WebFetchTool(Tool):
    name = "web_fetch"
    description = (
        "Download a web page and return its readable main content as text. " "HTTP(S) URLs only."
    )
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The http(s) URL to fetch."}},
        "required": ["url"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        url = str(args.get("url", "")).strip()
        if not url:
            return "Error: web_fetch needs a url."
        if not url.lower().startswith(("http://", "https://")):
            return "Error: only http(s) URLs are supported."
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=ctx.config.net_timeout_s) as response:
                raw = response.read(ctx.config.observe_cap_bytes * FETCH_MULTIPLE + 1)
        except Exception as exc:
            return f"Fetch error: {type(exc).__name__}: {exc}"
        try:
            from trafilatura import extract  # lazy: optional dependency

            text = extract(raw.decode("utf-8", errors="replace"), include_links=False)
        except Exception as exc:
            return f"Fetch error: extraction failed: {type(exc).__name__}: {exc}"
        if not text:
            return "Fetch error: no readable content extracted from that page."
        return truncate_bytes(text, ctx.config.observe_cap_bytes)
