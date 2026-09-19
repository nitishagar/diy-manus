"""LLM seam: extraction, retry-on-400, typed errors, import hygiene."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import httpx
import openai
import pytest

from manus.config import Config
from manus.llm import LLMClient, LLMError
from manus.util import extract_tool_call_from_prose


def make_client(monkeypatch, create_impl):
    """LLMClient whose openai SDK client is replaced by a scripted fake."""

    class FakeCompletions:
        create = staticmethod(create_impl)

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.base_url = base_url
            self.api_key = api_key
            self.chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return LLMClient(Config())


def fake_response(content="", tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def fake_tool_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(
        id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def test_first_tool_call_taken_when_multiple_returned(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return fake_response(
            tool_calls=[
                fake_tool_call("tool_a", '{"x": 1}', call_id="call_a"),
                fake_tool_call("tool_b", '{"y": 2}', call_id="call_b"),
            ],
            finish_reason="tool_calls",
        )

    client = make_client(monkeypatch, create)
    response = client.chat([{"role": "user", "content": "go"}], [])
    assert response.tool_call is not None
    assert response.tool_call.name == "tool_a"
    assert response.tool_call.id == "call_a"


def test_reasoning_effort_sent_when_configured(monkeypatch):
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return fake_response(content="ok")

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=staticmethod(create)))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    LLMClient(Config(reasoning_effort="none")).chat([{"role": "user", "content": "hi"}], [])
    assert seen["reasoning_effort"] == "none"


def test_bad_request_on_reasoning_effort_retries_without(monkeypatch):
    attempts = []

    def create(**kwargs):
        attempts.append(dict(kwargs))
        if "reasoning_effort" in kwargs:
            request = httpx.Request("POST", "http://test/v1/chat/completions")
            raise openai.BadRequestError(
                "Unknown field: reasoning_effort",
                response=httpx.Response(400, request=request),
                body=None,
            )
        return fake_response(content="ok")

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=staticmethod(create)))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    response = LLMClient(Config()).chat([{"role": "user", "content": "hi"}], [])
    assert response.content == "ok"
    assert len(attempts) == 2
    assert "reasoning_effort" in attempts[0]
    assert "reasoning_effort" not in attempts[1]


def test_bad_request_other_reason_is_typed_error(monkeypatch):
    def create(**kwargs):
        request = httpx.Request("POST", "http://test/v1/chat/completions")
        raise openai.BadRequestError(
            "model not found", response=httpx.Response(400, request=request), body=None
        )

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=staticmethod(create)))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    with pytest.raises(LLMError, match="rejected the request"):
        LLMClient(Config()).chat([{"role": "user", "content": "hi"}], [])


def test_unreachable_endpoint_is_actionable_llm_error(monkeypatch):
    request = httpx.Request("POST", "http://127.0.0.1:1/v1/chat/completions")

    def create(**kwargs):
        raise openai.APIConnectionError(request=request)

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=staticmethod(create)))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    client = LLMClient(Config(base_url="http://127.0.0.1:1/v1"))
    with pytest.raises(LLMError, match="Cannot reach the LLM endpoint"):
        client.chat([{"role": "user", "content": "hi"}], [])


def test_env_base_url_override_flows_to_client(monkeypatch):
    """The single config seam must reach the SDK client: a hosted endpoint is used
    only by setting MANUS_BASE_URL (spec invariant 8)."""
    captured = {}

    def create(**kwargs):
        return fake_response(content="ok")

    class FakeOpenAI:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=staticmethod(create)))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("MANUS_BASE_URL", "http://192.0.2.9:9999/v1")  # TEST-NET-1, never dialed
    LLMClient(Config.from_env()).chat([{"role": "user", "content": "hi"}], [])
    assert captured["base_url"] == "http://192.0.2.9:9999/v1"


def test_prose_json_fallback_recovers_tool_call():
    prose = (
        'I will write the file now. {"name": "file_write", '
        '"arguments": {"path": "a.txt", "content": "hi"}}'
    )
    call = extract_tool_call_from_prose(prose)
    assert call is not None
    assert call.name == "file_write"
    assert '"path"' in call.arguments and "a.txt" in call.arguments


def test_prose_fallback_ignores_json_without_name():
    assert extract_tool_call_from_prose('Here is data {"a": 1} and more') is None
    assert extract_tool_call_from_prose("no braces at all") is None
    assert extract_tool_call_from_prose("") is None


def test_import_hygiene_no_side_effects_on_empty_env():
    """Importing every manus module in a clean interpreter must not construct clients,
    touch the network, write files, or require any env (spec invariant 2)."""
    code = (
        "import os, sys\n"
        "violations = []\n"
        "FORBIDDEN = ('socket.connect', 'socket.getaddrinfo', 'socket.bind',\n"
        "             'socket.sendto', 'urllib.Request', 'subprocess.Popen',\n"
        "             'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir',\n"
        "             'os.symlink', 'os.link', 'os.chmod', 'os.truncate')\n"
        "def _audit(event, args):\n"
        "    if event in FORBIDDEN:\n"
        "        violations.append((event, str(args)[:120]))\n"
        "    elif event == 'open':\n"
        "        mode, flags = args[1] or '', args[2] or 0\n"
        "        if ('w' in mode or 'a' in mode or 'x' in mode or\n"
        "                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT |\n"
        "                         os.O_TRUNC | os.O_APPEND)):\n"
        "            violations.append((event, str(args)[:120]))\n"
        "sys.addaudithook(_audit)\n"
        "import importlib\n"
        "mods = ['manus', 'manus.config', 'manus.util', 'manus.llm', 'manus.agent', "
        "'manus.session', 'manus.trace', 'manus.__main__', "
        "'manus.tools', 'manus.tools.base', 'manus.tools.builtin', 'manus.tools.files', "
        "'manus.tools.shell', 'manus.tools.search', 'manus.tools.fetch', 'manus.tools.browser']\n"
        "for m in mods:\n"
        "    importlib.import_module(m)\n"
        # optional deps must stay lazy: importing the package may not pull them in
        "for lazy in ('ddgs', 'trafilatura', 'playwright', 'playwright.sync_api'):\n"
        "    assert lazy not in sys.modules, f'{lazy} imported at module load'\n"
        "assert not violations, f'import side effects: {violations}'\n"
        "print('HYGIENE OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "HYGIENE OK" in result.stdout
