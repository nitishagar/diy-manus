"""Shared fixtures: FakeLLM loop oracle + offline Config."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pytest

from manus.config import Config
from manus.llm import LLMResponse, ToolCall


@dataclass
class ScriptedLLM:
    """Deterministic LLM oracle: replays canned responses and records every call.

    Records a deep copy of `messages` at each call so append-only behavior can be
    asserted (the agent must never mutate already-sent history).
    """

    responses: List[LLMResponse] = field(default_factory=list)
    calls: List[List[dict]] = field(default_factory=list)

    def chat(self, messages, tool_schemas):
        self.calls.append(copy.deepcopy(messages))
        if not self.responses:
            return LLMResponse(content="", tool_call=None, finish_reason="stop")
        return self.responses.pop(0)


def tool_response(name: str, args: dict, call_id: str = "call_x", content: str = "") -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_call=ToolCall(name=name, arguments=json.dumps(args), id=call_id),
        finish_reason="tool_calls",
    )


@pytest.fixture
def offline_config(tmp_path: Path) -> Config:
    return Config(
        workspace=tmp_path / "ws",
        db_path=tmp_path / "sessions.db",
        max_steps=4,
        observe_cap_bytes=512,
        shell_timeout_s=5,
        net_timeout_s=2,
    )


@pytest.fixture
def scripted_llm():
    return ScriptedLLM()
