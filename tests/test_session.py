"""Session store: FTS5 round-trip, crash-readability, degradation, replay data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from manus.session import SessionStore


def test_fts5_available_and_probe(tmp_path: Path):
    conn = sqlite3.connect(str(tmp_path / "probe.db"))
    conn.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")  # must not raise locally
    conn.close()


def test_roundtrip_search_finds_events(tmp_path: Path):
    store = SessionStore(tmp_path / "s.db")
    run_id = store.start_run("find the deployment docs")
    store.add_event(
        run_id, 1, "tool", "web_search", {"query": "deploy"}, "Found kubernetes rollout docs", 120
    )
    store.add_event(run_id, 2, "tool", "file_write", {"path": "notes.md"}, "saved notes", 5)
    store.finish_run(run_id, "finished", "done")
    hits = store.search_text("kubernetes")
    assert "run" in hits and "kubernetes" in hits


def test_search_empty_db_reports_no_history(tmp_path: Path):
    store = SessionStore(tmp_path / "empty.db")
    assert store.search_text("anything") == "No history found for that query."


def test_crash_readable_per_event_commit(tmp_path: Path):
    path = tmp_path / "crash.db"
    store = SessionStore(path)
    run_id = store.start_run("task A")
    store.add_event(run_id, 1, "tool", "shell_exec", {"command": "ls"}, "file1\nfile2", 30)
    # simulate a crash: a brand-new store instance on the same file must see the event
    reopened = SessionStore(path)
    stored = reopened.get_run(run_id)
    assert stored is not None
    run, events = stored
    assert run[1] == "task A"
    assert len(events) == 1
    # columns: seq, kind, name, args_json, observation, elapsed_ms
    assert events[0][2] == "shell_exec"
    assert events[0][3] == '{"command": "ls"}'
    assert events[0][4] == "file1\nfile2"


def test_unwritable_db_degrades_without_raising(tmp_path: Path, capsys):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file")  # parent dir exists but child path is a file
    store = SessionStore(blocker / "child.db")  # mkdir(parent) will fail
    assert store.start_run("t") is None
    assert store.add_event(None, 1, "tool", "x", {}, "o", 1) is None
    assert store.search_text("q") == "No history available."
    assert store.list_runs() == []
    assert store.get_run(1) is None
    # degradation must be reported, not silent (spec invariant 9: trace loss is reported)
    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "session store unavailable" in captured.err


def test_missing_parent_dir_created(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "sessions.db"
    store = SessionStore(path)
    run_id = store.start_run("fresh location")
    store.add_event(run_id, 1, "tool", "file_read", {}, "contents", 4)
    assert path.exists()
    assert SessionStore(path).get_run(run_id) is not None


def test_list_runs_orders_recent_first(tmp_path: Path):
    store = SessionStore(tmp_path / "l.db")
    first = store.start_run("first task")
    second = store.start_run("second task")
    store.finish_run(first, "finished", "done")
    runs = store.list_runs()
    assert [r[0] for r in runs] == [second, first]
    assert runs[1][2] == "finished"


def test_recall_tool_uses_store(tmp_path: Path):
    from manus.config import Config
    from manus.tools.base import ToolContext
    from manus.tools.builtin import RecallTool

    store = SessionStore(tmp_path / "r.db")
    run_id = store.start_run("earlier run")
    store.add_event(run_id, 1, "tool", "web_fetch", {}, "quokka habitat details", 900)
    ctx = ToolContext(
        workspace=tmp_path,
        config=Config(workspace=tmp_path, db_path=tmp_path / "r.db"),
        session=store,
    )
    result = RecallTool().run({"query": "quokka"}, ctx)
    assert "quokka" in result
    assert RecallTool().run({"query": ""}, ctx).startswith("Error:")


def test_recall_without_session(tmp_path: Path):
    from manus.config import Config
    from manus.tools.base import ToolContext
    from manus.tools.builtin import RecallTool

    ctx = ToolContext(
        workspace=tmp_path, config=Config(workspace=tmp_path, db_path=tmp_path / "x.db")
    )
    assert RecallTool().run({"query": "past work"}, ctx) == "No history available."
