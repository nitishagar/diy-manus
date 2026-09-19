"""Terminal step trace: live progress on stderr, replay rendering for the CLI."""

from __future__ import annotations

import json
import sys
from typing import List, Sequence, Tuple


def args_summary(args: dict, limit: int = 64) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class StepTracer:
    """Prints one line per tool execution to stderr during a run."""

    def __init__(self, stream=None) -> None:
        self._stream = stream or sys.stderr
        self._seq = 0

    def run_start(self, task: str, model: str, workspace) -> None:
        print(
            f"─ manus · model {model} · workspace {workspace}\n─ task: {task}",
            file=self._stream,
        )

    def step(self, name: str, args: dict, elapsed_s: float, observation: str) -> None:
        self._seq += 1
        obs_bytes = len(observation.encode("utf-8", errors="replace"))
        print(
            f"#{self._seq} · {name}({args_summary(args)}) · {elapsed_s:.1f}s · {obs_bytes}B obs",
            file=self._stream,
        )

    def run_end(self, status: str, summary: str) -> None:
        print(f"─ done ({status})", file=self._stream)


def render_replay(run: Sequence, events: List[Tuple]) -> str:
    """Render a stored run for `--replay`: header + one line per stored event."""
    run_id, task, status, summary, started_at, finished_at = run
    lines = [f"run {run_id} · {status}", f"task: {task}"]
    for seq, kind, name, args_json, observation, elapsed_ms in events:
        try:
            args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError:
            args = {}
        head = observation.splitlines()[0][:100] if observation else ""
        lines.append(f"#{seq} · {name or kind}({args_summary(args)}) · {elapsed_ms}ms · {head}")
    if summary:
        lines.append(f"result: {summary}")
    return "\n".join(lines)
