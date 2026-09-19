"""CLI entry: `python -m manus "task"` — local run, step trace, replay, history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from manus import __version__
from manus.agent import Agent
from manus.config import Config, ConfigError
from manus.llm import LLMClient, LLMError
from manus.session import SessionStore
from manus.tools import default_registry
from manus.trace import StepTracer, render_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manus",
        description="A local-first general AI agent (DIY Manus). Runs fully on your machine.",
    )
    parser.add_argument("task", nargs="*", help="The task for the agent to perform.")
    parser.add_argument(
        "--workspace", help="Directory the agent works in (default ~/manus_workspace)."
    )
    parser.add_argument("--max-steps", type=int, help="Agent step limit (default 30).")
    parser.add_argument("--model", help="Model name for the LLM endpoint (default qwen3:4b).")
    parser.add_argument("--base-url", help="OpenAI-compatible LLM endpoint (default local ollama).")
    parser.add_argument(
        "--db", help="Session store path (default ~/.local/share/diy-manus/sessions.db)."
    )
    parser.add_argument("--list", action="store_true", help="List recent runs and exit.")
    parser.add_argument("--replay", type=int, metavar="ID", help="Show a stored run step by step.")
    parser.add_argument("--version", action="version", version=f"diy-manus {__version__}")
    return parser


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    return Config(
        base_url=args.base_url or cfg.base_url,
        api_key=cfg.api_key,
        model=args.model or cfg.model,
        max_steps=args.max_steps if args.max_steps is not None else cfg.max_steps,
        step_max_tokens=cfg.step_max_tokens,
        shell_timeout_s=cfg.shell_timeout_s,
        net_timeout_s=cfg.net_timeout_s,
        observe_cap_bytes=cfg.observe_cap_bytes,
        search_cap_results=cfg.search_cap_results,
        workspace=Path(args.workspace).expanduser() if args.workspace else cfg.workspace,
        reasoning_effort=cfg.reasoning_effort,
        db_path=Path(args.db).expanduser() if args.db else cfg.db_path,
        search_backend=cfg.search_backend,
        searxng_url=cfg.searxng_url,
    )


def _print_list(store: SessionStore) -> int:
    runs = store.list_runs()
    if not runs:
        print("No runs recorded yet.")
        return 0
    for run_id, task, status, summary in runs:
        short = (summary or task).replace("\n", " ")[:80]
        print(f"{run_id:>4}  {status:<10} {short}")
    return 0


def _print_replay(store: SessionStore, run_id: int) -> int:
    stored = store.get_run(run_id)
    if stored is None:
        print(f"No run {run_id} found.", file=sys.stderr)
        return 1
    print(render_replay(*stored))
    return 0


def _run_task(cfg: Config, task: str) -> int:
    workspace = cfg.workspace
    workspace.mkdir(parents=True, exist_ok=True)

    store = SessionStore(cfg.db_path)
    run_id = store.start_run(task)
    tracer = StepTracer()
    tracer.run_start(task, cfg.model, workspace)
    seq = 0

    def on_event(kind: str, name: str, args: dict, observation: str, elapsed_s: float) -> None:
        nonlocal seq
        seq += 1
        tracer.step(name, args, elapsed_s, observation)
        store.add_event(run_id, seq, kind, name, args, observation, int(elapsed_s * 1000))

    agent = Agent(
        llm=LLMClient(cfg),
        registry=default_registry(),
        config=cfg,
        session=store,
        on_event=on_event,
    )
    try:
        result = agent.run(task, workspace)
    except LLMError as exc:
        tracer.run_end("error", str(exc))
        store.finish_run(run_id, "error", str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tracer.run_end(result.status, result.summary)
    store.finish_run(run_id, result.status, result.summary)
    if result.summary:
        print(result.summary)
    if result.status != "finished":
        print(f"note: run ended with status {result.status}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    load_dotenv()  # entry-only: importing manus stays side-effect free
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return _print_list(SessionStore(Config.from_env().db_path))
    if args.replay is not None:
        return _print_replay(SessionStore(Config.from_env().db_path), args.replay)

    task = " ".join(args.task).strip()
    if not task:
        parser.print_usage(sys.stderr)
        print(
            'error: a task is required, e.g. manus "create hello.txt containing hi"',
            file=sys.stderr,
        )
        return 1

    try:
        cfg = _apply_overrides(Config.from_env(), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return _run_task(cfg, task)


if __name__ == "__main__":
    sys.exit(main())
