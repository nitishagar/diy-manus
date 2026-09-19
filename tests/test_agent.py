"""Agent loop semantics via the FakeLLM oracle: termination, guards, append-only, bounds."""

from __future__ import annotations

import copy

from manus.agent import Agent
from manus.config import Config
from manus.llm import LLMResponse, ToolCall
from manus.tools.base import Tool, ToolRegistry
from manus.tools.builtin import FinishTool
from tests.conftest import tool_response


class NoopTool(Tool):
    name = "noop"
    description = "does nothing"
    parameters = {"type": "object", "properties": {"arg": {"type": "string"}}, "required": []}

    def __init__(self):
        self.calls = []

    def run(self, args, ctx):
        self.calls.append(copy.deepcopy(args))
        return "ok"


class LoudTool(Tool):
    name = "loud"
    description = "returns oversized output"
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, args, ctx):
        return "x" * 10_000


class UnicodeTool(Tool):
    name = "unicode"
    description = "returns unicode"
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, args, ctx):
        return "héllo wörld ✓ 日本語 " * 3


def make_agent(scripted_llm, config, tools):
    registry = ToolRegistry(tools=[FinishTool()] + tools)
    return Agent(llm=scripted_llm, registry=registry, config=config)


def test_finish_ends_loop_with_summary(scripted_llm, offline_config):
    scripted_llm.responses = [tool_response("finish", {"summary": "all done"}, call_id="c1")]
    agent = make_agent(scripted_llm, offline_config, tools=[NoopTool()])
    result = agent.run("do the thing", offline_config.workspace)
    assert result.status == "finished"
    assert result.summary == "all done"
    assert result.steps == 1


def test_max_steps_terminates_run(scripted_llm):
    config = Config(workspace="/tmp/wsx", db_path="/tmp/dbx.db", max_steps=3)
    noop = NoopTool()
    scripted_llm.responses = [
        tool_response("noop", {"arg": str(i)}, call_id=f"c{i}") for i in range(10)
    ]
    agent = make_agent(scripted_llm, config, tools=[noop])
    result = agent.run("loop me", config.workspace)
    assert result.status == "max_steps"
    assert result.steps == 3
    assert len(noop.calls) == 3


def test_malformed_prose_recovers_via_fallback(scripted_llm, offline_config):
    prose = LLMResponse(
        content='Sure: {"name": "finish", "arguments": {"summary": "recovered"}}',
        tool_call=None,
        finish_reason="stop",
    )
    scripted_llm.responses = [prose]
    agent = make_agent(scripted_llm, offline_config, tools=[])
    result = agent.run("recover", offline_config.workspace)
    assert result.status == "finished"
    assert result.summary == "recovered"


def test_three_malformed_turns_abort(scripted_llm, offline_config):
    scripted_llm.responses = [
        LLMResponse(content=f"plain text {i}", tool_call=None, finish_reason="stop")
        for i in range(3)
    ]
    agent = make_agent(scripted_llm, offline_config, tools=[])
    result = agent.run("hopeless", offline_config.workspace)
    assert result.status == "aborted_malformed"
    assert result.steps == 3
    assert "Aborted" in result.summary


def test_invalid_json_arguments_strike_then_recover(scripted_llm, offline_config):
    bad = LLMResponse(
        content="",
        tool_call=ToolCall(name="noop", arguments="not json at all", id="c1"),
        finish_reason="tool_calls",
    )
    scripted_llm.responses = [bad, tool_response("finish", {"summary": "ok"}, call_id="c2")]
    agent = make_agent(scripted_llm, offline_config, tools=[NoopTool()])
    result = agent.run("try", offline_config.workspace)
    assert result.status == "finished"


def test_identical_call_guard_aborts(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("noop", {"arg": "same"}, call_id=f"c{i}") for i in range(5)
    ]
    noop = NoopTool()
    agent = make_agent(scripted_llm, offline_config, tools=[noop])
    result = agent.run("stuck", offline_config.workspace)
    assert result.status == "aborted_loop"
    assert "identical tool call" in result.summary
    assert len(noop.calls) == 2  # third identical call is refused before execution


def test_different_args_do_not_trigger_loop_guard(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("noop", {"arg": str(i)}, call_id=f"c{i}") for i in range(3)
    ] + [tool_response("finish", {"summary": "done"}, call_id="cf")]
    agent = make_agent(scripted_llm, offline_config, tools=[NoopTool()])
    result = agent.run("varied", offline_config.workspace)
    assert result.status == "finished"


def test_history_is_append_only(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("noop", {"arg": "a"}, call_id="c1"),
        tool_response("noop", {"arg": "b"}, call_id="c2"),
        tool_response("finish", {"summary": "ok"}, call_id="c3"),
    ]
    agent = make_agent(scripted_llm, offline_config, tools=[NoopTool()])
    agent.run("history", offline_config.workspace)
    snapshots = scripted_llm.calls
    assert len(snapshots) == 3
    for earlier, later in zip(snapshots, snapshots[1:]):
        assert later[: len(earlier)] == earlier  # never rewritten, only appended
    assert len(snapshots[1]) > len(snapshots[0])


def test_exactly_one_tool_call_executed_per_iteration(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("noop", {"arg": "a"}, call_id="c1"),
        tool_response("noop", {"arg": "b"}, call_id="c2"),
        tool_response("finish", {"summary": "ok"}, call_id="c3"),
    ]
    noop = NoopTool()
    agent = make_agent(scripted_llm, offline_config, tools=[noop])
    result = agent.run("steady", offline_config.workspace)
    assert result.status == "finished"
    assert result.steps == 3
    assert len(noop.calls) == 2  # one execution per iteration, finish excluded


def test_oversized_observation_truncated_with_marker(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("loud", {}, call_id="c1"),
        tool_response("finish", {"summary": "ok"}, call_id="c2"),
    ]
    agent = make_agent(scripted_llm, offline_config, tools=[LoudTool()])
    agent.run("big", offline_config.workspace)
    history = scripted_llm.calls[-1]
    tool_msgs = [m for m in history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    body = tool_msgs[0]["content"]
    assert len(body.encode("utf-8")) <= offline_config.observe_cap_bytes
    assert "…[truncated]" in body


def test_unicode_observation_handled(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("unicode", {}, call_id="c1"),
        tool_response("finish", {"summary": "ok ✓"}, call_id="c2"),
    ]
    agent = make_agent(scripted_llm, offline_config, tools=[UnicodeTool()])
    result = agent.run("unicode", offline_config.workspace)
    assert result.status == "finished"
    history = scripted_llm.calls[-1]
    tool_msgs = [m for m in history if m.get("role") == "tool"]
    assert "日本語" in tool_msgs[0]["content"]


def test_unknown_tool_counts_as_malformed(scripted_llm, offline_config):
    scripted_llm.responses = [
        tool_response("does_not_exist", {"try": str(i)}, call_id=f"c{i}") for i in range(3)
    ]
    agent = make_agent(scripted_llm, offline_config, tools=[NoopTool()])
    result = agent.run("unknown", offline_config.workspace)
    assert result.status == "aborted_malformed"


def test_empty_task_still_runs(scripted_llm, offline_config):
    scripted_llm.responses = [tool_response("finish", {"summary": "nothing to do"}, call_id="c1")]
    agent = make_agent(scripted_llm, offline_config, tools=[])
    result = agent.run("", offline_config.workspace)
    assert result.status == "finished"
    assert result.summary == "nothing to do"


def test_on_event_fires_per_tool_execution(scripted_llm, offline_config):
    events = []
    scripted_llm.responses = [
        tool_response("noop", {"arg": "a"}, call_id="c1"),
        tool_response("finish", {"summary": "ok"}, call_id="c2"),
    ]
    registry = ToolRegistry(tools=[FinishTool(), NoopTool()])
    agent = Agent(
        llm=scripted_llm,
        registry=registry,
        config=offline_config,
        on_event=lambda kind, name, args, obs, elapsed: events.append((kind, name)),
    )
    result = agent.run("events", offline_config.workspace)
    assert result.status == "finished"
    assert events == [("tool", "noop")]
