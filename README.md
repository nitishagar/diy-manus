# DIY Manus — a local-first general AI agent

A working, self-hosted take on [Manus](https://manus.im): an agent that plans, uses tools
(shell, files, web), and delivers real files — running **entirely on your machine**. No cloud
API keys, no subscriptions, no data leaving your network.

```
┌──────────── you ────────────┐
│  manus "research X and      │
│  write a summary.md"        │
└──────────────┬──────────────┘
               ▼
┌────────── agent loop ───────┐   one tool call per iteration,
│  think → act → observe      │   append-only context, todo.md
│  (repeat until finish)      │   recitation, bounded outputs
└──────────────┬──────────────┘
               ▼
┌─────────── tools ───────────┐
│ shell · file · web_search   │   LLM: ollama (OpenAI-compatible)
│ web_fetch · browser · recall│   search: keyless DuckDuckGo
└──────────────┬──────────────┘   memory: SQLite + FTS5
               ▼
      deliverables in your workspace + replayable session trace
```

## 90-second quickstart

Requires [Python 3.10+](https://python.org), [ollama](https://ollama.com), and `make`.

```bash
git clone https://github.com/nitishagar/diy-manus.git
cd diy-manus

make setup                                   # venv + deps + ollama check + model pull
make run TASK="create hello.txt containing hi"
make smoke                                   # end-to-end local test
```

That's the whole setup. The agent thinks out loud in your terminal (one line per step),
writes deliverables into `~/manus_workspace`, and stores a replayable trace locally.

> On a CPU-only laptop expect ~30–60 s per agent step; a task is typically 3–15 steps.
> Have a GPU or want a stronger model? Point `MANUS_BASE_URL`/`MANUS_MODEL` at any
> OpenAI-compatible endpoint — the code is identical.

## What it inherited from Manus

| Manus behavior | DIY Manus |
|---|---|
| Agent loop: pick one action → execute in sandbox → observe → repeat | ✅ same shape; max-steps and guards force termination |
| `todo.md` planning, re-stated to stay on track ("recitation") | ✅ agent maintains todo.md via file tools |
| File system as externalized memory | ✅ workspace files + SQLite session history |
| Fixed tool space, one tool per iteration | ✅ fixed registry of 11 tools |
| Session replay of every step | ✅ `manus --replay <id>` + live stderr trace |
| Deliverables: real files, not just chat | ✅ everything lands in your workspace |
| Cloud VM sandbox + browser + deploy tools | 🚧 local processes now; Docker sandbox on the roadmap |

## Tools

| Tool | What it does |
|---|---|
| `shell_exec` | bash in the workspace; merged output, size-capped, killed at timeout (process group) |
| `file_read` / `file_write` / `file_list` | workspace-confined file ops (traversal and symlink escapes refused) |
| `web_search` | keyless search via [ddgs](https://pypi.org/project/ddgs/), or your self-hosted SearXNG |
| `web_fetch` | bounded download + main-content extraction ([trafilatura](https://trafilatura.readthedocs.io)) |
| `browser_navigate` / `browser_snapshot` / `browser_click` | optional local Playwright Chromium; degrades gracefully if not installed |
| `recall` | full-text search over past local sessions (SQLite FTS5) |
| `finish` | end the task with a summary |

Small local models sometimes answer in prose instead of tool JSON; the loop detects that,
attempts one JSON-recovery pass, and aborts cleanly after repeated failures instead of
looping forever.

## Configuration

Everything runs local **by default** — zero env vars required. Overrides (via environment
or `.env`, see [.env.example](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `MANUS_BASE_URL` | `http://127.0.0.1:11434/v1` | any OpenAI-compatible endpoint |
| `MANUS_MODEL` | `qwen2.5:3b` | tool-calling capable model; `qwen3:4b`+ for stronger machines |
| `MANUS_API_KEY` | `ollama` | only needed for hosted endpoints |
| `MANUS_WORKSPACE` | `~/manus_workspace` | where the agent works |
| `MANUS_DB` | `~/.local/share/diy-manus/sessions.db` | session memory |
| `MANUS_MAX_STEPS` | `30` | hard step limit per run |
| `MANUS_SEARCH_BACKEND` | `ddgs` | or `searxng` + `MANUS_SEARXNG_URL` |

Past runs and traces:

```bash
manus --list            # recent runs
manus --replay 3        # step-by-step replay of run 3
```

## Safety notes (read this)

- The shell tool executes real commands on your machine **inside your workspace
  directory**. It is a convenience, not a security boundary: a model tricked by malicious
  web content could ask it to run harmful commands. Don't point the agent at untrusted
  tasks you wouldn't type yourself; the roadmap adds a Docker sandbox seam.
- File tools are hard-confined to the workspace (including symlink escapes), and shell
  output is size-capped and time-limited — but the shell itself is not jailed.
- Everything stays on your machine unless you set a hosted `MANUS_BASE_URL`.

## Development

```bash
make install   # dev deps
make check     # flake8 + mypy + pytest (62 tests, fully offline — no ollama needed)
make format    # black
make lint      # flake8 + mypy
```

The test suite drives the agent loop with a scripted FakeLLM, so it never touches a model
or the network. `make smoke` is the only test that uses ollama.

## Roadmap

- Docker-sandboxed shell tool (pluggable `Sandbox` seam)
- Local web UI with Manus-style session replay
- Scheduled/recurring tasks
- Multi-agent flows for wide research

## License

MIT
