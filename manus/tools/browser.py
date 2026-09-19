"""Optional browser tools (Playwright). Always registered; degrade to clear
"unavailable" observations when the library or the Chromium binary is missing."""

from __future__ import annotations

from manus.tools.base import Tool, ToolContext
from manus.util import truncate_bytes

INSTALL_HINT = (
    "browser tool unavailable: {reason}. To enable, run: "
    "pip install playwright && playwright install chromium"
)

# Shared across browser tool calls within one process: the page opened by
# browser_navigate is the one browser_click / browser_snapshot act on.
_state: dict = {}


def _unavailable(reason: str) -> str:
    return INSTALL_HINT.format(reason=reason)


def _launch(ctx: ToolContext):
    """Launch (or reuse) a headless Chromium page. Raises on any missing piece."""
    from playwright.sync_api import sync_playwright

    if _state.get("page") is not None:
        return _state["page"]
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    _state.update(playwright=playwright, browser=browser, page=page)
    return page


class BrowserNavigateTool(Tool):
    name = "browser_navigate"
    description = (
        "Open a URL in a local headless browser. Use before browser_click/browser_snapshot."
    )
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The http(s) URL to open."}},
        "required": ["url"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        url = str(args.get("url", "")).strip()
        if not url.lower().startswith(("http://", "https://")):
            return "Error: browser_navigate needs an http(s) URL."
        try:
            page = _launch(ctx)
            page.goto(url, timeout=ctx.config.net_timeout_s * 1000, wait_until="domcontentloaded")
            title = page.title()
            return truncate_bytes(f"Opened {url}\nTitle: {title}", ctx.config.observe_cap_bytes)
        except Exception as exc:
            return _unavailable(f"{type(exc).__name__}: {exc}")


class BrowserSnapshotTool(Tool):
    name = "browser_snapshot"
    description = (
        "Return the current page's visible text and numbered interactive elements "
        "(for use with browser_click)."
    )
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, args: dict, ctx: ToolContext) -> str:
        try:
            page = _launch(ctx)
            js = (
                "els => els.map((el, i) => `${i}: ${(el.innerText || el.value || "
                "el.getAttribute('aria-label') || el.tagName).toString().trim().slice(0, 80)}`)"
            )
            elements = page.eval_on_selector_all(
                "a, button, input, select, textarea, [onclick], [role=button]", js
            )
            text = page.inner_text("body")
            listing = "\n".join(str(e) for e in elements[:50])
            return truncate_bytes(
                f"--- page text ---\n{text}\n--- clickable elements ---\n{listing}",
                ctx.config.observe_cap_bytes,
            )
        except Exception as exc:
            return _unavailable(f"{type(exc).__name__}: {exc}")


class BrowserClickTool(Tool):
    name = "browser_click"
    description = "Click an interactive element by its index from the last browser_snapshot."
    parameters = {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Element index from browser_snapshot."}
        },
        "required": ["index"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        try:
            page = _launch(ctx)
            index = int(args.get("index", -1))
            if index < 0:
                return "Error: browser_click needs a non-negative element index."
            selector = "a, button, input, select, textarea, [onclick], [role=button]"
            elements = page.query_selector_all(selector)
            if index >= len(elements):
                return (
                    f"Error: element index {index} out of range; the page has "
                    f"{len(elements)} interactive elements. Take a fresh browser_snapshot."
                )
            elements[index].click(timeout=ctx.config.net_timeout_s * 1000)
            page.wait_for_load_state("domcontentloaded", timeout=ctx.config.net_timeout_s * 1000)
            return f"Clicked element {index}."
        except Exception as exc:
            return _unavailable(f"{type(exc).__name__}: {exc}")
