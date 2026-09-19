"""The Manus-style agent loop: one tool call per iteration, append-only context."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from manus.config import Config
from manus.llm import LLMClient, ToolCall
from manus.tools.base import SessionLike, Tool, ToolContext, ToolRegistry
from manus.util import extract_tool_call_from_prose, truncate_bytes

# Compact on purpose: prompt tokens are re-evaluated every step on CPU-only
# machines, where prompt processing is as costly as generation.
SYSTEM_PROMPT = (
    "You are Manus, an AI agent working on the user's machine.\n"
    "- Each turn call exactly one tool.\n"
    "- For multi-step tasks keep todo.md updated via file tools and re-read it when lost.\n"
    "- Adapt after errors; keep going until the goal is met.\n"
    "- As soon as the user's goal is met, call finish with a one-sentence summary. "
    "Never repeat work that is already done."
)

MALFORMED_STRIKES = 3
LOOP_STRIKES = 3

NO_TOOL_CALL_ADVICE = (
    "Error: no tool call recognized in that reply. You must respond by calling exactly "
    "one tool (or finish). Repeat the action as a proper tool call."
)

BAD_JSON_ADVICE = (
    "Error: tool arguments were not valid JSON. Resend the call with a JSON object "
    "for arguments."
)

MALFORMED_ABORT_NOTICE = "Aborted: the model produced no usable tool call in {n} consecutive turns."

LOOP_ABORT_NOTICE = (
    "Aborted: the model repeated the identical tool call {n} times with no progress."
)

MAX_STEPS_NOTICE = (
    "Stopped at the step limit ({n}). Partial progress is described by the last observations."
)


@dataclass
class RunResult:
    summary: str
    status: str  # "finished" | "max_steps" | "aborted_malformed" | "aborted_loop"
    steps: int


def _canonical_args(args: dict) -> str:
    return json.dumps(args, sort_keys=True, ensure_ascii=False)


def _parse_arguments(raw: str) -> Optional[dict]:
    """Parse a tool-call arguments string; recover a JSON object from prose wrappers."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    recovered = extract_tool_call_from_prose(raw or "")
    if recovered is not None:
        try:
            parsed = json.loads(recovered.arguments)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        config: Config,
        session: Optional[SessionLike] = None,
        on_event=None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._config = config
        self._session = session
        self._on_event = on_event  # callable(kind, name, args, observation, elapsed_s)

    def run(self, task: str, workspace: Path) -> RunResult:
        ctx = ToolContext(workspace=Path(workspace), config=self._config, session=self._session)
        messages: List[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        schemas = self._registry.schemas()

        malformed = 0
        last_key: Optional[tuple] = None
        repeats = 0

        for step in range(1, self._config.max_steps + 1):
            response = self._llm.chat(messages, schemas)

            call = response.tool_call
            if call is None:
                call = extract_tool_call_from_prose(response.content)
            if call is None:
                malformed += 1
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": NO_TOOL_CALL_ADVICE})
                if malformed >= MALFORMED_STRIKES:
                    return self._end(
                        "aborted_malformed",
                        MALFORMED_ABORT_NOTICE.format(n=MALFORMED_STRIKES),
                        step,
                    )
                continue

            args = _parse_arguments(call.arguments)
            if args is None:
                malformed += 1
                messages.append(self._assistant_tool_message(call, response.content))
                messages.append(self._tool_message(call, step, BAD_JSON_ADVICE))
                if malformed >= MALFORMED_STRIKES:
                    return self._end(
                        "aborted_malformed",
                        MALFORMED_ABORT_NOTICE.format(n=MALFORMED_STRIKES),
                        step,
                    )
                continue

            key = (call.name, _canonical_args(args))
            if key == last_key:
                repeats += 1
            else:
                repeats = 1
                last_key = key
            if repeats >= LOOP_STRIKES:
                notice = LOOP_ABORT_NOTICE.format(n=LOOP_STRIKES)
                messages.append({"role": "user", "content": notice})
                return self._end("aborted_loop", notice, step)

            tool = self._registry.get(call.name)
            if tool is None:
                malformed += 1
                known = ", ".join(t.name for t in self._registry.tools)
                messages.append(self._assistant_tool_message(call, response.content))
                messages.append(
                    self._tool_message(
                        call, step, f"Error: unknown tool {call.name!r}. Available: {known}."
                    )
                )
                if malformed >= MALFORMED_STRIKES:
                    return self._end(
                        "aborted_malformed",
                        MALFORMED_ABORT_NOTICE.format(n=MALFORMED_STRIKES),
                        step,
                    )
                continue

            if call.name == "finish":
                summary = tool.run(args, ctx)
                return RunResult(summary=summary, status="finished", steps=step)

            started = time.monotonic()
            observation = self._execute(tool, args, ctx)
            elapsed = time.monotonic() - started
            observation = truncate_bytes(observation, self._config.observe_cap_bytes)
            if self._on_event is not None:
                self._on_event("tool", call.name, args, observation, elapsed)
            messages.append(self._assistant_tool_message(call, response.content))
            messages.append(self._tool_message(call, step, observation))

        return self._end(
            "max_steps",
            MAX_STEPS_NOTICE.format(n=self._config.max_steps),
            self._config.max_steps,
        )

    def _execute(self, tool: Tool, args: dict, ctx: ToolContext) -> str:
        try:
            return tool.run(args, ctx)
        except Exception as exc:  # tool failures are observations, never loop crashes
            return f"Tool error: {type(exc).__name__}: {exc}"

    def _assistant_tool_message(self, call: ToolCall, content: str) -> dict:
        message: dict = {"role": "assistant", "content": content}
        message["tool_calls"] = [
            {
                "id": call.id or "call_missing",
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
        ]
        return message

    def _tool_message(self, call: ToolCall, step: int, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call.id or f"call_{step}", "content": content}

    def _end(self, status: str, summary: str, steps: int) -> RunResult:
        return RunResult(summary=summary, status=status, steps=steps)
