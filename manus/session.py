"""Local session store: SQLite + FTS5. Crash-readable via per-event commits.

Every write degrades to a no-op-with-warning if the DB is unavailable — a broken
store never aborts a run; trace loss is reported instead.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    args_json TEXT NOT NULL DEFAULT '',
    observation TEXT NOT NULL DEFAULT '',
    elapsed_ms INTEGER NOT NULL DEFAULT 0
);
"""


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path).expanduser()
        self._conn: Optional[sqlite3.Connection] = None
        self._warned = False

    # -- internal ---------------------------------------------------------

    def _connect(self) -> Optional[sqlite3.Connection]:
        if self._conn is not None:
            return self._conn
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5("
                "observation, name UNINDEXED, run_id UNINDEXED)"
            )
            conn.commit()
            self._conn = conn
            return conn
        except (sqlite3.Error, OSError) as exc:
            self._warn(f"session store unavailable at {self._path}: {exc}")
            return None

    def _warn(self, message: str) -> None:
        if not self._warned:
            print(f"warning: {message}", file=sys.stderr)
            self._warned = True

    # -- writes (all degrade to no-op) -------------------------------------

    def start_run(self, task: str) -> Optional[int]:
        conn = self._connect()
        if conn is None:
            return None
        try:
            cursor = conn.execute(
                "INSERT INTO runs (task, status, started_at) VALUES (?, 'running', ?)",
                (task, time.time()),
            )
            conn.commit()
            row_id = cursor.lastrowid
            return int(row_id) if row_id is not None else None
        except sqlite3.Error as exc:
            self._warn(f"could not record run start: {exc}")
            return None

    def finish_run(self, run_id: Optional[int], status: str, summary: str) -> None:
        if run_id is None:
            return
        conn = self._connect()
        if conn is None:
            return
        try:
            conn.execute(
                "UPDATE runs SET status = ?, summary = ?, finished_at = ? WHERE id = ?",
                (status, summary, time.time(), run_id),
            )
            conn.commit()
        except sqlite3.Error as exc:
            self._warn(f"could not record run end: {exc}")

    def add_event(
        self,
        run_id: Optional[int],
        seq: int,
        kind: str,
        name: str,
        args: dict,
        observation: str,
        elapsed_ms: int,
    ) -> None:
        if run_id is None:
            return
        conn = self._connect()
        if conn is None:
            return
        try:
            args_json = json.dumps(args, ensure_ascii=False)[:2000]
            conn.execute(
                "INSERT INTO events (run_id, seq, kind, name, args_json, observation, elapsed_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, seq, kind, name, args_json, observation[:20_000], elapsed_ms),
            )
            conn.execute(
                "INSERT INTO events_fts (observation, name, run_id) VALUES (?, ?, ?)",
                (observation[:20_000], name, run_id),
            )
            conn.commit()  # per-event commit: a crashed run leaves a readable trace
        except sqlite3.Error as exc:
            self._warn(f"could not record event: {exc}")

    # -- reads (empty results on unavailable store) --------------------------

    def search_text(self, query: str) -> str:
        """FTS5 search over past observations; the recall tool's backend."""
        conn = self._connect()
        if conn is None:
            return "No history available."
        rows: List[Tuple] = []  # stays empty when every query form fails (e.g. corrupt index)
        escaped = '"' + query.replace('"', '""') + '"'
        for match_query in (query, escaped):
            try:
                rows = conn.execute(
                    "SELECT run_id, name, snippet(events_fts, 0, '[', ']', '…', 12) "
                    "FROM events_fts WHERE events_fts MATCH ? LIMIT 8",
                    (match_query,),
                ).fetchall()
                break
            except sqlite3.Error:
                continue
        if not rows:
            return "No history found for that query."
        lines = [f"[run {run_id}] {name or 'event'}: {snippet}" for run_id, name, snippet in rows]
        return "\n".join(lines)

    def list_runs(self) -> List[Tuple[int, str, str, str]]:
        conn = self._connect()
        if conn is None:
            return []
        try:
            return conn.execute(
                "SELECT id, task, status, summary FROM runs ORDER BY id DESC LIMIT 30"
            ).fetchall()
        except sqlite3.Error as exc:
            self._warn(f"could not list runs: {exc}")
            return []

    def get_run(self, run_id: int) -> Optional[Tuple[Any, List[Tuple]]]:
        conn = self._connect()
        if conn is None:
            return None
        try:
            run = conn.execute(
                "SELECT id, task, status, summary, started_at, finished_at FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            events = conn.execute(
                "SELECT seq, kind, name, args_json, observation, elapsed_ms FROM events "
                "WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
            return run, events
        except sqlite3.Error as exc:
            self._warn(f"could not read run: {exc}")
            return None
