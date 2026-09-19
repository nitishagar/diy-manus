"""Regression tests for defects found in the implementation review (2026-09-19).

Each test pins a fix: truncation with tiny caps, FTS total-failure degradation,
tool_call_id consistency, --db applying to --list/--replay, and typed LLM errors
on retry failure / empty responses.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import httpx
import openai
import pytest

from manus import __main__ as cli
from manus.agent import Agent
from manus.config import Config
from manus.llm import LLMError, LLMResponse, ToolCall
from manus.session import SessionStore
from manus.tools.base import Tool, ToolRegistry
from manus.tools.builtin import FinishTool
from manus.util import TRUNCATION_MARKER, truncate_bytes
from tests.test_llm import make_client

MARKER_BYTES = len(TRUNCATION_MARKER.encode("utf-8"))


def test_truncate_bytes_honours_caps_smaller_than_marker():
    for cap in (1, 5, 11, 50, 100):
        out = truncate_bytes("A" * 1000, cap)
        assert len(out.encode("utf-8")) <= max(cap, MARKER_BYTES), cap
        assert TRUNCATION_MARKER in out


def test_search_text_degrades_when_every_fts_query_fails(tmp_path):
    class BrokenConn:
        """FTS MATCH always fails, e.g. on a corrupted index."""

        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args):
            if "MATCH" in sql:
                raise sqlite3.OperationalError("database disk image is malformed")
            return self._conn.execute(sql, *args)

    store = SessionStore(tmp_path / "s.db")
    run_id = store.start_run("t")
    store.add_event(run_id, 1, "tool", "x", {}, "some observation", 1)
    store._conn = BrokenConn(store._conn)
    assert store.search_text("anything") == "No history found for that query."


class _Noop(Tool):
    name = "noop"
    description = "noop"
    parameters = {"type": "object", "properties": {}}

    def run(self, args, ctx):
        return "ok"


class _FakeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def chat(self, messages, tool_schemas):
        self.calls.append([dict(m) for m in messages])
        return self.responses.pop(0)


def test_tool_call_id_consistent_when_model_omits_id(tmp_path):
    responses = [
        LLMResponse(
            content="", tool_call=ToolCall(name="noop", arguments="{}", id=""), finish_reason="t"
        ),
        LLMResponse(
            content="",
            tool_call=ToolCall(name="finish", arguments='{"summary":"x"}', id=""),
            finish_reason="t",
        ),
    ]
    agent = Agent(
        llm=_FakeLLM(responses),
        registry=ToolRegistry(tools=[FinishTool(), _Noop()]),
        config=Config(max_steps=4),
    )
    agent.run("t", tmp_path)
    history = agent._llm.calls[-1]  # messages as sent on the finish step
    assistant = [m for m in history if m.get("role") == "assistant" and "tool_calls" in m][0]
    tool_msg = [m for m in history if m.get("role") == "tool"][0]
    assert assistant["tool_calls"][0]["id"] == tool_msg["tool_call_id"]


def test_cli_db_flag_applies_to_list_and_replay(tmp_path, monkeypatch, capsys):
    db = tmp_path / "other.db"
    store = SessionStore(db)
    run_id = store.start_run("recorded task")
    store.add_event(run_id, 1, "tool", "file_write", {"path": "x"}, "Wrote", 3)
    store.finish_run(run_id, "finished", "done")
    monkeypatch.setenv("MANUS_DB", str(tmp_path / "default.db"))  # --db must win over env

    assert cli.main(["--list", "--db", str(db)]) == 0
    assert "done" in capsys.readouterr().out  # the run's summary is listed
    assert cli.main(["--replay", str(run_id), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "recorded task" in out and "file_write" in out


def test_retry_failure_after_strip_is_typed_llm_error(monkeypatch):
    attempts = []

    def create(**kwargs):
        attempts.append("reasoning_effort" in kwargs)
        request = httpx.Request("POST", "http://test/v1/chat/completions")
        message = (
            "Unknown field: reasoning_effort" if "reasoning_effort" in kwargs else "still rejected"
        )
        raise openai.BadRequestError(
            message, response=httpx.Response(400, request=request), body=None
        )

    client = make_client(monkeypatch, create)
    with pytest.raises(LLMError, match="even without reasoning_effort"):
        client.chat([{"role": "user", "content": "hi"}], [])
    assert attempts == [True, False]


def test_empty_choices_is_typed_llm_error(monkeypatch):
    client = make_client(monkeypatch, lambda **kwargs: SimpleNamespace(choices=[]))
    with pytest.raises(LLMError, match="no choices"):
        client.chat([{"role": "user", "content": "hi"}], [])
