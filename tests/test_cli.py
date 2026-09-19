"""CLI: usage errors, list/replay, run wiring with a fake agent, env override seam."""

from __future__ import annotations

from pathlib import Path

import pytest

from manus import __main__ as cli
from manus.agent import RunResult
from manus.config import Config
from manus.llm import LLMError
from manus.session import SessionStore


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch):
    db = tmp_path / "cli" / "sessions.db"
    workspace = tmp_path / "ws"
    monkeypatch.setenv("MANUS_DB", str(db))
    monkeypatch.setenv("MANUS_WORKSPACE", str(workspace))
    return db, workspace


def test_empty_task_is_usage_error(cli_env, capsys):
    assert cli.main([]) == 1
    assert "task is required" in capsys.readouterr().err


def test_list_empty(cli_env, capsys):
    assert cli.main(["--list"]) == 0
    assert "No runs recorded" in capsys.readouterr().out


def test_replay_missing_run(cli_env, capsys):
    assert cli.main(["--replay", "99"]) == 1
    assert "No run 99" in capsys.readouterr().err


def test_env_override_seam(cli_env):
    db, workspace = cli_env
    cfg = Config.from_env()
    assert cfg.db_path == db
    assert cfg.workspace == workspace


def test_env_model_override(monkeypatch):
    monkeypatch.setenv("MANUS_MODEL", "llama3:8b")
    assert Config.from_env().model == "llama3:8b"


def test_config_defaults_are_local(monkeypatch):
    """With zero env config, defaults must describe a fully local setup — no cloud
    endpoint, no API key requirement (spec invariants 1 and 8)."""
    for var in ("MANUS_BASE_URL", "MANUS_API_KEY", "MANUS_MODEL", "MANUS_WORKSPACE", "MANUS_DB"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.from_env()
    assert cfg.base_url == "http://127.0.0.1:11434/v1"
    assert cfg.api_key == "ollama"
    assert cfg.model == "qwen2.5:3b"
    assert cfg.workspace == Path("~/manus_workspace").expanduser()


def test_run_writes_trace_and_result(cli_env, monkeypatch, capsys):
    db, _workspace = cli_env

    class FakeAgent:
        def __init__(self, llm, registry, config, session=None, on_event=None):
            self.on_event = on_event

        def run(self, task, workspace):
            self.on_event("tool", "file_write", {"path": "out.txt"}, "Wrote 2 bytes", 0.4)
            return RunResult(summary="created the file", status="finished", steps=2)

    monkeypatch.setattr(cli, "Agent", FakeAgent)
    assert cli.main(["make the file"]) == 0
    assert "created the file" in capsys.readouterr().out

    store = SessionStore(db)
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0][1] == "make the file"
    assert runs[0][2] == "finished"
    _run, events = store.get_run(runs[0][0])
    assert [(e[2], e[4]) for e in events] == [("file_write", "Wrote 2 bytes")]


def test_aborted_run_exit_code(cli_env, monkeypatch, capsys):
    class FakeAgent:
        def __init__(self, llm, registry, config, session=None, on_event=None):
            pass

        def run(self, task, workspace):
            return RunResult(summary="Stopped at the step limit (4).", status="max_steps", steps=4)

    monkeypatch.setattr(cli, "Agent", FakeAgent)
    assert cli.main(["stuck task"]) == 2
    assert "max_steps" in capsys.readouterr().err


def test_llm_error_exits_2_with_message(cli_env, monkeypatch, capsys):
    class FakeAgent:
        def __init__(self, llm, registry, config, session=None, on_event=None):
            pass

        def run(self, task, workspace):
            raise LLMError("Cannot reach the LLM endpoint at http://x (model m).")

    monkeypatch.setattr(cli, "Agent", FakeAgent)
    assert cli.main(["hello"]) == 2
    assert "Cannot reach the LLM endpoint" in capsys.readouterr().err


def test_workspace_created_with_parents(cli_env, monkeypatch):
    _db, workspace = cli_env
    assert not workspace.exists()

    class FakeAgent:
        def __init__(self, llm, registry, config, session=None, on_event=None):
            pass

        def run(self, task, workspace):
            return RunResult(summary="ok", status="finished", steps=1)

    monkeypatch.setattr(cli, "Agent", FakeAgent)
    assert cli.main(["bootstrap"]) == 0
    assert workspace.is_dir()


def test_replay_after_run(cli_env, monkeypatch, capsys):
    class FakeAgent:
        def __init__(self, llm, registry, config, session=None, on_event=None):
            self.on_event = on_event

        def run(self, task, workspace):
            self.on_event("tool", "shell_exec", {"command": "ls"}, "file1", 0.1)
            return RunResult(summary="listed files", status="finished", steps=1)

    monkeypatch.setattr(cli, "Agent", FakeAgent)
    assert cli.main(["list files"]) == 0
    assert cli.main(["--replay", "1"]) == 0
    out = capsys.readouterr().out
    assert "run 1 · finished" in out
    assert "shell_exec" in out
    assert "listed files" in out
