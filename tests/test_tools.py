"""Tool suite: confinement (incl. symlinks), bounds, reaping, degradation, registry."""

from __future__ import annotations

import subprocess
import sys
import types
import urllib.request
from pathlib import Path

import pytest

from manus.config import Config
from manus.tools import default_registry
from manus.tools.browser import BrowserNavigateTool, BrowserSnapshotTool
from manus.tools.fetch import WebFetchTool
from manus.tools.files import FileListTool, FileReadTool, FileWriteTool, resolve_confined
from manus.tools.search import WebSearchTool
from manus.tools.shell import ShellExecTool
from manus.tools.base import ToolContext


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    config = Config(
        workspace=workspace,
        db_path=tmp_path / "db.db",
        observe_cap_bytes=1024,
        shell_timeout_s=3,
        net_timeout_s=2,
    )
    return ToolContext(workspace=workspace, config=config)


# ---------- file tools: confinement ----------


def test_file_write_read_roundtrip_and_parent_creation(ctx):
    write = FileWriteTool().run({"path": "a/b/c.txt", "content": "hello"}, ctx)
    assert "Wrote" in write
    read = FileReadTool().run({"path": "a/b/c.txt"}, ctx)
    assert read == "hello"


def test_traversal_refused(ctx):
    for bad in ["../../etc/passwd", "/etc/passwd", "a/../../../etc/passwd"]:
        result = FileWriteTool().run({"path": bad, "content": "x"}, ctx)
        assert result.startswith("Error:"), bad
        assert "escapes the workspace" in result


def test_symlink_escape_refused(ctx):
    outside = ctx.workspace.parent / "outside_secret.txt"
    outside.write_text("secret")
    link = ctx.workspace / "innocent.txt"
    link.symlink_to(outside)
    read = FileReadTool().run({"path": "innocent.txt"}, ctx)
    assert read.startswith("Error:")
    assert "escapes the workspace" in read
    write = FileWriteTool().run({"path": "innocent.txt", "content": "overwrite"}, ctx)
    assert write.startswith("Error:")
    assert outside.read_text() == "secret"  # untouched


def test_file_list_and_empty_file(ctx):
    (ctx.workspace / "sub").mkdir()
    (ctx.workspace / "sub" / "z.txt").write_text("x")
    (ctx.workspace / "sub" / "a.txt").write_text("")
    listing = FileListTool().run({"path": "sub"}, ctx)
    assert listing.splitlines() == ["a.txt", "z.txt"]
    empty = FileReadTool().run({"path": "sub/a.txt"}, ctx)
    assert empty == "(empty file)"


def test_unicode_and_long_single_line_truncation(ctx):
    payload = "日本語テキスト" * 5000  # single line, multi-byte, well past the cap
    FileWriteTool().run({"path": "big.txt", "content": payload}, ctx)
    read = FileReadTool().run({"path": "big.txt"}, ctx)
    assert len(read.encode("utf-8")) <= ctx.config.observe_cap_bytes
    assert "…[truncated]" in read
    assert "日本語" in read  # cut on a character boundary, not mid-codepoint


def test_resolve_confined_returns_root_for_empty(ctx):
    assert resolve_confined(ctx.workspace, "") == ctx.workspace.resolve()


# ---------- shell tool: bounds and reaping ----------


def test_shell_basic_output_and_exit_code(ctx):
    result = ShellExecTool().run({"command": "echo hello; ls missing-file"}, ctx)
    assert result.startswith("exit=")
    assert "hello" in result
    assert "ls: cannot access" in result  # stderr merged into the single pipe


def test_shell_empty_output(ctx):
    result = ShellExecTool().run({"command": "true"}, ctx)
    assert "exit=0" in result
    assert "(no output)" in result


def test_shell_output_cap_stops_command(ctx):
    result = ShellExecTool().run({"command": "yes | head -c 200000"}, ctx)
    assert "output exceeded the size cap" in result
    body = result.split("\n", 1)[1]
    assert len(body.encode("utf-8")) <= ctx.config.observe_cap_bytes + 64


def test_shell_timeout_kills_process_group(ctx):
    marker = "sleep 5.317"
    result = ShellExecTool().run({"command": f"echo started; {marker} & wait"}, ctx)
    assert "exceeded the" in result
    # the backgrounded child must have been reaped with the group
    pgrep = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True, timeout=10)
    assert pgrep.returncode != 0, f"orphaned child still running: {pgrep.stdout}"


def test_shell_needs_command(ctx):
    assert ShellExecTool().run({}, ctx).startswith("Error:")


# ---------- search tool: backends and degradation ----------


def test_web_search_ddgs_backend_mocked(ctx, monkeypatch):
    fake_ddgs = types.ModuleType("ddgs")

    class FakeDDGS:
        def __init__(self, timeout=None):
            self.timeout = timeout

        def text(self, query, max_results):
            assert query == "local llm agents"
            assert max_results == ctx.config.search_cap_results
            return [
                {"title": "Result", "href": "https://example.com/a", "body": "snippet"},
                {"title": "R2", "href": "https://example.com/b", "body": "s2"},
            ]

    fake_ddgs.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_ddgs)
    result = WebSearchTool().run({"query": "local llm agents"}, ctx)
    assert "1. Result" in result
    assert "https://example.com/a" in result


def test_web_search_failure_is_observation_not_exception(ctx, monkeypatch):
    fake_ddgs = types.ModuleType("ddgs")

    class FakeDDGS:
        def __init__(self, timeout=None):
            raise RuntimeError("rate limit hit")

    fake_ddgs.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_ddgs)
    result = WebSearchTool().run({"query": "anything"}, ctx)
    assert result.startswith("Search error:")
    assert "rate limit" in result


def test_web_search_searxng_backend_switch(ctx, monkeypatch):
    config = Config(
        workspace=ctx.workspace,
        db_path=ctx.config.db_path,
        search_backend="searxng",
        searxng_url="http://127.0.0.1:8888",
        net_timeout_s=2,
    )
    local_ctx = ToolContext(workspace=ctx.workspace, config=config)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"results": [{"title": "S", "url": "http://x", "content": "c"}]}'

    def fake_urlopen(request, timeout=None):
        assert request.full_url.startswith("http://127.0.0.1:8888/search?")
        assert "format=json" in request.full_url
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = WebSearchTool().run({"query": "q"}, local_ctx)
    assert "1. S" in result


# ---------- fetch tool ----------


def test_web_fetch_extracts_text(ctx):
    # example.com is small and stable; net request is real but tiny.
    # Assert on extraction success rather than exact copy, which the page may edit.
    result = WebFetchTool().run({"url": "https://example.com"}, ctx)
    assert not result.startswith("Fetch error")
    assert len(result) > 20


def test_web_fetch_refuses_non_http(ctx):
    result = WebFetchTool().run({"url": "file:///etc/passwd"}, ctx)
    assert result.startswith("Error:")
    assert "http(s)" in result


def test_web_fetch_unreachable_is_observation(ctx):
    result = WebFetchTool().run({"url": "http://127.0.0.1:1/"}, ctx)
    assert result.startswith("Fetch error:")


# ---------- browser tools: degradation at both failure layers ----------


def test_browser_unavailable_when_import_missing(ctx, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)  # import raises
    result = BrowserNavigateTool().run({"url": "https://example.com"}, ctx)
    assert result.startswith("browser tool unavailable:")
    assert "playwright install chromium" in result


def test_browser_unavailable_at_call_time(ctx, monkeypatch):
    fake = types.ModuleType("playwright.sync_api")

    def broken_sync_playwright():
        raise RuntimeError("Executable doesn't exist — chromium not installed")

    fake.sync_playwright = broken_sync_playwright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    result = BrowserSnapshotTool().run({}, ctx)
    assert result.startswith("browser tool unavailable:")
    assert "chromium not installed" in result


# ---------- registry ----------


def test_default_registry_fixed_and_wellformed():
    registry = default_registry()
    names = [t.name for t in registry.tools]
    assert len(names) == len(set(names))
    assert "finish" in names and "recall" in names
    assert "shell_exec" in names and "file_write" in names
    assert "web_search" in names and "browser_navigate" in names
    for schema in registry.schemas():
        assert schema["name"]
        assert schema["description"]
        assert schema["parameters"]["type"] == "object"


def test_registry_get_unknown_returns_none():
    assert default_registry().get("nope") is None
