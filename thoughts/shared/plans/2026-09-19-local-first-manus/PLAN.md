<!-- SIGNPOST | 2/5: PLAN | single source of truth; implementation must conform — divergence means amending this file in the same change, not improvising
     Prev: IMPLICIT_SPEC.md | Next: PLAN_VALIDATION.md -->
# Local-first DIY Manus Implementation Plan
scale: medium

## Overview
Replace the broken cloud-dependent LangGraph toy with a local-first Manus-style general agent package (`manus/`): an OpenAI-compatible LLM loop with one-tool-call-per-iteration and append-only context, local tools (shell, files, keyless search, fetch, optional browser), SQLite+FTS5 session memory, a CLI with replay, a one-command local run setup, and docs/Pages. Four stages map to the three research hard cores; docs/setup is the fourth stage.

## Current State
Repo `nitishagar/diy-manus` @ `1cdcceb` (main): single-file agent `mini_manus.py` + 2 test files + Makefile/pyproject. Facts verified in the research doc: requirements.txt is ResolutionImpossible (mem0ai==0.1.6 vs langchain-openai==0.2.1); tests fail at collection without real cloud keys (module-level clients at `mini_manus.py:26-28`); ollama 0.21.2 serves tool calls from `qwen3:4b` (also aliased `gpt-4o-mini:latest`) at ~4–5 tok/s CPU; `ddgs` + `trafilatura` verified on Python 3.14; docker socket unavailable to user; `gh` CLI authenticated. Verification Surface: `make test` / `make lint` / `make check` / **test-one** `pytest tests/<file> -q`; no oracles/fixtures exist (research → Gaps).

## Desired End State
Observable: on a machine with ollama running and the repo cloned, `bash scripts/setup.sh` succeeds; `make run TASK="create hello.txt containing hi"` performs a multi-step local run with a visible step trace and produces the file in the workspace; `make check` is green (lint + unit tests, no cloud, no ollama required); `make smoke` runs a tiny end-to-end local task and reports PASS (or SKIP with reason if ollama is down); `python -m manus --list` / `--replay <id>` shows persisted traces; README + docs/ site document all of it; all pushed to GitHub with Pages serving the landing page.

## What We're NOT Doing
- No Docker sandboxing in v1 (user account lacks docker socket permission — `docker ps` → permission denied); documented as roadmap with exact future design hook (a `Sandbox` seam behind shell tool config).
- No web UI / server (roadmap). No multi-agent flows, no scheduled tasks, no deploy tools (Manus features deliberately out of scope for v1).
- No model downloads during `make check`/tests (unit tests are model-free).
- No keeping of the old LangGraph/mem0/Tavily stack (uninstallable as pinned; git history preserves it; README documents the replacement).

## Approach
`manus/` package, stdlib-first. **LLM seam** (`manus/llm.py`): the `openai` SDK pointed at an env-driven `base_url` — the single config seam that keeps local default / hosted-for-testing true without code branches. **Loop** (`manus/agent.py`): Manus's loop shape — stable system prompt, append-only messages, exactly one tool call executed per iteration, observation appended, finish tool ends — with three small-model guards: (a) one JSON-extraction fallback pass for prose-wrapped calls before counting malformed output, (b) malformed-output counter (3 strikes → abort with partial result), (c) identical-call guard (same tool+args 3 consecutive times → abort with observation trail). Per-step `max_tokens` cap; `reasoning_effort` is config-driven with a strip-and-retry-on-400 pass (invariant 8; ollama needs "none", OpenAI uses "minimal", some servers reject the field). **Tools** (`manus/tools/`): fixed registry, always-present tool list (no dynamic mutation); shell via `subprocess.Popen(start_new_session=True)` with incremental bounded read (cap+1 byte triggers kill), `os.killpg` reaping on timeout, cwd=workspace; file tools confined via resolved-path `is_relative_to` check against the resolved workspace root; search via `ddgs` with `MANUS_SEARCH_BACKEND=searxng` optional; fetch via `trafilatura`; browser tools lazy-import playwright and catch call-time failures (binary missing ≠ import missing) returning a structured "unavailable" observation; `recall` queries FTS5 over persisted traces. **Sessions** (`manus/session.py`): SQLite WAL, per-event commits (crash-readable), every write degrades to no-op with end-of-run warning if DB unavailable. **CLI** (`manus/__main__.py`): loads `.env` (dotenv) only at entry (import stays side-effect-free), step trace to stderr, result to stdout, `--list`/`--replay`. **Setup** (`scripts/setup.sh`, Makefile): venv, deps, ollama reachability check, optional `qwen3:4b` pull, `make smoke` end-to-end. Old `mini_manus.py` + old tests deleted.

## Design Analysis
- **Invariants → mechanism**: (1) zero-cloud default → local defaults in `config.py`, no key paths; criterion: any unit test run on empty env. (2) import side-effect-free → no client construction at module level anywhere; criterion: tests import package on empty env. (3) loop terminates → max-steps + malformed strikes + identical-call strikes + per-tool timeout (shell wall-clock deadline; network tools via `net_timeout_s`); criteria: FakeLLM infinite-prose and infinite-loop cases end; mocked-hang tool tests return error observations. (4) one-tool-call/append-only → loop takes first tool_call; never rewrites `messages`; criterion: FakeLLM history assertion. (5) workspace confinement → resolve+`is_relative_to`; criterion: traversal + symlink tests. (6) bounded execution → incremental read cap + killpg + observation truncation with marker (applied at tool level and again in the agent loop to every observation); criteria: cap test, orphan test, long-unicode truncation test, agent-level oversized-observation truncation test. (7) graceful degradation → call-time catch-alls returning structured observations; criterion: missing-browser-tool test with mocked import failure. (8) single config seam → `config.py` only; criterion: hosted-endpoint unit test via env override. (9) traceability → per-event commit; criterion: crash-readable test (write events, simulate crash, read). (10) local memory → `recall` FTS5 tool; criterion: FTS5 probe + recall test. (11) minimal deps → runtime deps only `openai, ddgs, trafilatura, python-dotenv`.
- **Failure & concurrency**: timed-out shell processes are killed by process-group (`killpg`), pipe drained/closed in `finally`; session writes wrapped, DB failure never aborts a run (warning on stderr + end-of-run note); search/fetch failures become error observations, loop continues. Single-threaded agent — no locking beyond SQLite WAL defaults.
- **Simplicity guardrails**: no DI framework (tool registry is a plain list of instances); no retry library (one strip-and-retry on 400); no caching layer (ollama prefixes cache server-side); no config file format (env only, `.env` documented); no bespoke crypto/parsing (JSON via stdlib; extraction via trafilatura). Retained state: sessions DB only.
- **Blast radius**: greenfield package; deleted files (`mini_manus.py`, `tests/test_mini_manus.py`, `tests/test_imports.py`) have exactly three in-repo consumers — `Makefile:17`/`Makefile:19`/`Makefile:22` (flake8/mypy/black on `mini_manus.py`, retargeted to `manus/` + `tests/` in Stage A alongside the deletion) — plus README usage references (`README.md:24`, `README.md:77`) updated in the docs stage. Rollback: git revert of the implementation commit restores the old tree.
- **Interrogation**: *What could break?* — ollama API drift (`reasoning_effort` rejection → strip-and-retry covers), ddgs rate limits (error observation covers), trafilatura fetch failures (error observation), pytest on 3.14 (deps verified installed here). *Riskiest step* — Stage A loop semantics against a real 4B model; earliest cheap check: FakeLLM unit suite before any live call, then `make smoke` with max-steps=4. *Options not taken* — LangGraph retained (uninstallable pins + opaque routing for small models); plain httpx instead of openai SDK (rejected: retries/streaming hand-rolled for no gain); mem0-OSS memory (rejected: needs embedder model pull; FTS5 meets invariant 10 with zero pulls); Playwright as core tool (rejected on 700 MB RAM / install heft — optional).
- **Verification design**: Gaps closed from research: FakeLLM fixture (loop oracle), workspace-confinement tests, termination tests, local smoke (`make smoke`) as the end-to-end local check. Oracles: FakeLLM scripted sequences for loop semantics; Manus loop description (one call/iteration, append-only) as behavioral reference. No observability beyond stderr trace needed at this scale.
- **Default choices**: black line-length 100, flake8, mypy config kept from pyproject with `python_version` raised 3.9 → 3.10 to match the package floor; pytest layout kept; Python ≥3.10 per ddgs/trafilatura support (3.14 verified locally). Deviations: none from repo conventions except replacing the stack (documented above).

## Scale Cost Model
Dominant cost unit: **LLM output tokens per task** (generation at ~4–5 tok/s CPU is the only slow resource; everything else is ms-scale).

| Operation (weight) | small (5-step task) | mid (15-step) | large (30-step, max) |
|---|---|---|---|
| LLM step call (w=1/step) | 5 × ≤150 out-tok ≈ 750 | 15 × 150 ≈ 2.2K | 30 × 150 ≈ 4.5K |
| Tool exec (local, ms–s) | 5 | 15 | 30 |
| Observation re-injection (bounded 10 KB/step) | 50 KB context | 150 KB | 300 KB |
| **weighted total (output tok)** | **≈750 (~3 min)** | **≈2.2K (~8 min)** | **≈4.5K (~17 min)** |

Weighted total grows linearly with steps but is capped by max-steps=30 and per-step output cap; it does not grow with data size or user count (single user). ollama's prefix KV cache keeps per-step prefill cheap since the context is append-only. Verdict: design accepted — bounded by explicit caps, flat in all other dimensions. Measured in the actual environment by `make smoke` wall-time (target: <15 min for the 4-step smoke task on this machine; baseline: this plan's measurements).

## Phase 1 (Stage A): Agent core — the reliable loop
Hard core: reliable tool-calling loop on small/slow local models.
### Changes
#### `manus/__init__.py`
Package marker only (no side effects).
#### `manus/config.py`
Env dataclass: `base_url` (default `http://127.0.0.1:11434/v1`), `api_key` (default `ollama`), `model` (default `qwen3:4b`), `max_steps` (30), `step_max_tokens` (512), `shell_timeout_s` (60), `net_timeout_s` (30), `observe_cap_bytes` (10_240), `search_cap_results` (5), `workspace` (default `~/manus_workspace`, home-anchored), `reasoning_effort` (default `none`, `""` disables sending the field), `db_path` (default `~/.local/share/diy-manus/sessions.db`). All read from `MANUS_*` env; constructed on demand, never at import.
#### `manus/llm.py`
`chat(messages, tools, cfg) -> LLMResponse` over `openai.OpenAI(base_url, api_key)`; sends `max_tokens`, `reasoning_effort` when configured; on 400 mentioning the field, retries without it; extracts first `tool_calls` entry or returns prose content; never raises past a typed `LLMError` with actionable message (endpoint unreachable / auth / malformed).
#### `manus/tools/base.py`
`Tool` dataclass: `name, description, parameters (JSON schema dict), run(args: dict, ctx: ToolContext) -> str`. `ToolContext`: workspace path + config. `ToolRegistry`: fixed ordered list; `schemas()` for the API; `get(name)`.
#### `manus/tools/builtin.py`
`finish_tool`: `finish(summary: str)` → ends loop. `recall_tool`: searches past session events via session store (wired in Stage C; until then returns "no history" observation — implemented in Stage C; placeholder per design so the tool list never changes).
#### `manus/agent.py`
`Agent.run(task, workspace) -> RunResult(summary, steps, status)`:
- System prompt (stable string, no timestamps): Manus-style instructions — maintain `todo.md` via file tools for non-trivial tasks; work step-by-step; one action per turn; finish with a summary; keep going after errors.
- Append-only `messages`; per iteration: `llm.chat` → if no tool call: JSON-extract fallback (first `{...}` block with `name`/`arguments` keys); still nothing → append error observation, increment malformed strikes (3 → abort). Identical (tool, args identical after JSON canonicalization with sorted keys) 3× consecutive → abort. Execute exactly one tool via registry with try/except → observation string (truncated per cap, `…[truncated]` marker). Append observation. Persist event (Stage C). Stop on `finish`/max-steps.
#### Files removed (this phase)
`mini_manus.py`, `tests/test_mini_manus.py`, `tests/test_imports.py`: the legacy suite fails at collection without cloud keys (verified 2026-09-19: `openai.OpenAIError` at pytest collection; deps uninstallable per research) and must be removed here — Phase 1's `make test` criterion is unsatisfiable while they exist.
#### `Makefile` (retargeted this phase)
`test`/`lint`/`format`/mypy target `manus/` + `tests/` instead of the deleted `mini_manus.py` (current consumers: `Makefile:17`, `Makefile:19`, `Makefile:22`) — same phase as the deletion, otherwise `make lint`/`make check` break.
### Success Criteria
- [x] Local: `pytest tests/test_agent.py -q` → all pass; covers: loop termination (finish, max-steps), malformed-prose fallback then 3-strike abort, identical-call guard, append-only history assertion (no message mutated), one-tool-per-iteration, agent-level observation truncation per cap with `…[truncated]` marker (fake tool returns > cap bytes), empty task, unicode observation. A miss localizes to: `manus/agent.py` loop logic. ✓ `11 passed` (part of 22 total)
- [x] Local: `pytest tests/test_llm.py -q` → FakeLLM + mocked openai client: first-tool-call extraction, prose-JSON fallback, 400-strip-retry, endpoint-unreachable typed error, import-hygiene (zero clients constructed while importing every `manus` module on empty env). A miss localizes to: `manus/llm.py` (or whichever module constructs at import). ✓ `8 passed`
- [x] End-to-end: `make lint` + `make test` (full suite) → flake8 clean, mypy clean, n passed 0 failed. ✓ `Success: no issues found in 8 source files` · `FLAKE8_CLEAN` · `black: 12 files unchanged` · `22 passed in 0.68s`
- [ ] Manual: none (no live model needed in this stage).

## Phase 2 (Stage B): Tools — safe local execution
Hard core: safe local tool execution.
### Changes
#### `manus/tools/files.py`
`file_read(path)`, `file_write(path, content)`, `file_list(path)` — all paths resolved and checked `is_relative_to(workspace.resolve())` (catches `..` and symlink escape); write creates parent dirs; read returns content truncated with marker; errors become observations, not exceptions.
#### `manus/tools/shell.py`
`shell_exec(command)`: `Popen(["bash","-lc",cmd], cwd=workspace, start_new_session=True, stderr=subprocess.STDOUT)` — a single merged output pipe (two unmerged pipes can deadlock: a child blocked writing a full stderr pipe while the read loop waits on stdout), read incrementally under a wall-clock deadline, stopping at cap+1 (then `killpg(SIGKILL)`); deadline expiry → `killpg`, reap, return partial output + timeout notice; pipe closed in `finally`; exit code and merged output in observation.
#### `manus/tools/search.py`
`web_search(query)`: backend switch — default `ddgs.DDGS(timeout=cfg.net_timeout_s).text(query, max_results=cfg.search_cap_results)` → formatted title/url/snippet block; `MANUS_SEARCH_BACKEND=searxng` → `GET {MANUS_SEARXNG_URL}/search?q&format=json` with the same timeout; failures (rate limit, timeout, unreachable) → error observation.
#### `manus/tools/fetch.py`
`web_fetch(url)`: HTML fetched via `urllib.request.urlopen(url, timeout=cfg.net_timeout_s)` — `trafilatura.fetch_url` has no timeout parameter (verified on trafilatura 2.2.0) — then `trafilatura.extract` (markdown-ish text), truncated with marker; failures (timeout, unreachable, nothing extractable) → error observation.
#### `manus/tools/browser.py`
`browser_navigate(url)`, `browser_click(index)`, `browser_snapshot()` — lazy `import playwright` inside `run()`; any failure (module missing, chromium binary missing, navigation error) → structured observation "browser tool unavailable: …" with install hint. Tools always registered.
### Success Criteria
- [x] Local: `pytest tests/test_tools.py -q` → all pass; covers: traversal refusal (`../../etc/passwd`, absolute outside, **symlink escape**), parent-dir creation, shell cap (generate >cap bytes → observation capped + no full buffer), shell timeout with backgrounded child reaped (`pgrep` assertion), empty output, unicode long-line truncation marker, search/fetch failure observations including mocked timeout/hang, browser unavailable observation (mocked import + call-time failure), searxng backend switch (mocked HTTP). A miss localizes to: the named tool module. ✓ `21 passed`
- [x] End-to-end: `make lint && make test` → clean + green. ✓ `FLAKE8_CLEAN` · `Success: no issues found in 13 source files` · `43 passed in 4.73s`
- [ ] Manual: none.

## Phase 3 (Stage C): Sessions, recall, CLI — all-local wiring
Hard core: all-local service wiring.
### Changes
#### `manus/session.py`
SQLite (`sqlite3`, WAL) at `cfg.db_path`, with the DB parent directory created before connect (a fresh `~/.local/share/diy-manus/` must not silently degrade every run to trace-loss): `runs(id, task, status, summary, started_at, finished_at)`, `events(id, run_id, seq, kind, name, args_json, observation, elapsed_ms)`; insert run at start, insert per event, commit per event (crash-readable); `search_events(query)` via FTS5 virtual table + triggers (probe `CREATE VIRTUAL TABLE` in a test — availability is [V] locally, not assumed); every method degrades to no-op-with-warning on `sqlite3.Error`/unwritable path; `list_runs`, `get_run` for replay.
#### `manus/trace.py`
`StepTracer`: prints `#3 · shell_exec("ls -la") · 0.4s · 132B obs` style lines to stderr during runs; `render_replay(run, events)` for `--replay`.
#### `manus/__main__.py`
Entry: `load_dotenv()` (entry-only — invariant 2 held), argparse: `task` positional (empty → error + usage), `--workspace`, `--max-steps`, `--model`, `--base-url`, `--list`, `--replay ID`, `--db`. Wire recall tool to session store. Create the workspace directory (parents included) at run start when missing. Exit codes: 0 success/finish, 1 usage, 2 aborted run (with partial summary printed).
### Success Criteria
- [ ] Local: `pytest tests/test_session.py tests/test_cli.py -q` → all pass; covers: FTS5 probe + recall search round-trip, crash-readable (insert events, open second connection, read), DB-unavailable degradation (unwritable path → run proceeds with warning), fresh-DB creation (missing parent dir → created, events persist and replay), empty-DB `recall` → "no history" observation, `--list`/`--replay` output, empty-task usage error, env override seam (workspace/model honored), workspace root auto-created with parents when missing. A miss localizes to: `manus/session.py` or `manus/__main__.py`.
- [ ] End-to-end: `make check` → lint+mypy+tests green.
- [ ] Manual: run `python -m manus "write a two-line haiku to haiku.txt" --max-steps 4` against local ollama; observe trace lines; `--replay` the run. (Live-model check; also covered automated by Stage D smoke.)

## Phase 4 (Stage D): Local run setup, docs, Pages
### Changes
#### `scripts/setup.sh`
idempotent: ensure venv (`.venv`), `pip install -r requirements.txt`, check `curl 127.0.0.1:11434/api/tags` (warn with instructions if down), `ollama pull qwen3:4b` if missing, optional `--with-browser` → `playwright install chromium`. `--check` mode: verify only.
#### `Makefile` (updated)
`setup` (bash scripts/setup.sh), `run TASK="..."` (python -m manus), `smoke` (the task `create hello.txt containing hi` via `python -m manus --workspace $(SMOKE_DIR) --max-steps 4`; PASS requires the produced `hello.txt` present in SMOKE_DIR; prints SMOKE PASS / SMOKE SKIP(ollama down) / FAIL + exit code), `check`/`test`/`lint`/`format` kept semantics.
#### `requirements.txt` / `requirements-dev.txt`
runtime: `openai>=1.40`, `ddgs>=9`, `trafilatura>=1.8`, `python-dotenv>=1.0`; dev: pytest, pytest-mock, pytest-cov, flake8, black, mypy (all verified installable on Python 3.14 locally; ddgs/trafilatura verified functional).
#### `.env.example`
Rewritten: `MANUS_BASE_URL/MANUS_MODEL/MANUS_API_KEY/MANUS_MAX_STEPS/MANUS_WORKSPACE/MANUS_SEARCH_BACKEND/MANUS_SEARXNG_URL` with local defaults commented; hosted-key variant documented as the "test with a hosted model" path.
#### `README.md` (rewrite) + `docs/`
README: local-first hero (zero cloud keys), 90-second quickstart (ollama → setup → run), architecture diagram, feature table vs Manus, safety notes (shell-not-a-security-boundary), limits notes (per-step `step_max_tokens` cap — very long tool-call arguments can hit it and count toward malformed-output strikes; 10 KB observation cap), roadmap (Docker sandbox, web UI, scheduled tasks). `docs/index.html` static landing page (same content, page-grade) for GitHub Pages.
#### GitHub Pages
Commit and push all changes to `main` first (no co-author attribution, per repo convention). Enable via `gh api repos/nitishagar/pages -X POST -f source='{"branch":"main","path":"/docs"}'` (or settings fallback), verify 200 on the published URL.
### Success Criteria
- [ ] Local: `bash scripts/setup.sh --check` → exit 0 with per-item OK/MISSING lines on this machine.
- [ ] End-to-end: `make smoke` → `SMOKE PASS` (task completed, file produced in smoke workspace) within the cost-model budget; `SMOKE SKIP` only if ollama is down (documented).
- [ ] End-to-end: `make check` → green after all changes.
- [ ] Manual: GitHub Pages URL loads with the landing page.

## Testing Strategy
Unit (offline, deterministic): FakeLLM scripted tool-call sequences as the loop oracle (termination, append-only, one-call-per-iteration, guards); tool tests in tmp workspaces (confinement incl. symlink, incremental cap, process-group reaping, truncation markers, unicode/empty/oversized boundaries); session tests on tmp DBs (FTS5 probe, crash-readable, degrade-to-noop); CLI tests via subprocess invocation. Integration (local, optional): `make smoke` — the only test that touches ollama, skip-with-reason when down; never runs in CI without ollama. Spec edges covered: 3 (termination) via FakeLLM cases + tool-timeout tests; 4 (append-only) via history assertion; 5 (confinement) via traversal/symlink tests; 6 (bounds) via tool-level cap/reap tests + agent-level truncation test; 7 (degradation) via mocked-failure tests; 9 (crash-readable) via cross-connection read; 10 (recall) via FTS round-trip + empty-DB "no history" observation.

## Amendments
- AMENDED 2026-09-19 Phase 1 [factual]: requirements.txt / requirements-dev.txt rewritten in Phase 1 instead of Phase 4 — the user requires "working commits"; leaving ResolutionImpossible pins in intermediate commits would make every pre-Stage-D commit uninstallable. Same file contents as Phase 4 specified; no mechanism change. — evidence: research doc Evidence Ledger (ResolutionImpossible, verified 2026-09-19).

## References
- Research: `thoughts/shared/research/2026-09-19-local-first-manus.md` (Evidence Ledger, Verification Surface, Workload Envelope)
- Spec: `thoughts/shared/plans/2026-09-19-local-first-manus/IMPLICIT_SPEC.md`
- Manus loop/tool features: manus.im blog "Context Engineering for AI Agents"; x1xhlol/system-prompts-and-models-of-ai-tools (leaked v1 tools)
- Local stack facts: docs.ollama.com/openai; pypi ddgs; trafilatura docs (all cited in research doc)
