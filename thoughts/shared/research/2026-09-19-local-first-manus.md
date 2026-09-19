---
date: 2026-09-19T20:25:40+05:30
researcher: ZCode (GLM-5.3-Flash main + GLM-5.3-Flash subagents)
git_commit: 1cdcceb092d5cdc33a227816309e5559f5d9cd08
branch: main
repository: git@github.com:nitishagar/diy-manus.git
topic: "Working DIY Manus implementation with full local run setup — update existing repo so the whole setup runs locally (LLM, search, memory, tools), incorporating Manus's most important features; docs + GitHub page"
tags: [research, codebase, agent-loop, ollama, local-first, tools]
scale: medium
status: complete
last_updated: 2026-09-19
last_updated_by: ZCode
---

# Research: Local-first DIY Manus (update of nitishagar/diy-manus)

## Research Question
"Working DIY Manus implementation with full local run setup … incorporate most important features with keeping the main grounded feature of running the whole setup locally as key and working backwards from it." User additions: existing implementation at github.com/nitishagar/diy-manus "needs update"; Manus is exactly https://manus.im; docs + GitHub page; no co-author attribution on commits; a test API key may be requested from the user at the very end.

## Intent
> Lifted from the user; `not stated` where silent. A record of what was asked — not a spec.
- **Problem**: The current diy-manus repo is a cloud-dependent research-only toy (OpenAI + Mem0 cloud + Tavily), so nothing about it runs locally; it also does not implement what makes Manus Manus (general tool use, planning, deliverables).
- **Proposed outcome**: A working DIY Manus implementation whose entire setup runs locally, incorporating Manus's most important features, with docs and a GitHub page; existing repo updated (not thrown away).
- **Constraints**: whole setup runs locally (grounded feature, work backwards from it); v2.7 research→plan→implement loop from nitishagar/claude-files; no co-author attribution in commits; API key only for testing, requested from user at the very end.
- **Open questions**:
  1. Which local LLM(s) to target as default? (partially answerable from environment — see Verification Surface / envelope)
  2. How far to go on sandboxing tool execution (Docker unavailable to user account — see findings)?
  3. Web UI (Manus-style replay) vs CLI-only for v1?
  4. Which browser capability level (HTTP fetch vs full Playwright)?

## Summary
The repo as published cannot even be installed: its pins are mutually unsatisfiable (`ResolutionImpossible`), and its tests fail at collection without real cloud API keys because all three clients are constructed at module import. Manus's defining mechanics are documented (official blog + leaked v1 tools): a single-action agent loop against a sandbox, todo.md planning with recitation, file-system-as-context, append-only event stream, one tool call per iteration, ~50 tool calls per average task. A local-first equivalent is buildable on this machine today: ollama 0.21.2 already serves OpenAI-compatible tool calling from the pre-pulled qwen3-4B (aliased `gpt-4o-mini:latest`), `ddgs` provides keyless local search, `trafilatura` provides page extraction, SQLite/FTS5 provides keyless session memory, and all were verified working on Python 3.14 here. The binding constraint is CPU inference speed (~4 tok/s measured), so the design must be output-token-frugal. Docker is running but the user account lacks socket permission, so container-based pieces must be optional. Two hard problems dominate: (1) a tool-calling loop reliable enough for small local models, (2) safe local tool execution (workspace sandboxing, timeouts, output truncation).

## Detailed Findings

### Current repo state (all `file:line` [V] — read in full)
- Single-file agent `mini_manus.py` (315 lines): LangGraph StateGraph with planner → research(Tavily) → writer nodes; `route_next_step` parses the planner's decision out of the emoji-decorated step log (`mini_manus.py:192-213`) — decision carried as display text, not structured state.
- All three cloud clients constructed at module level: `ChatOpenAI(model="gpt-4o-mini")` (`mini_manus.py:26`), `MemoryClient(api_key=…)` (`mini_manus.py:27`), `TavilyClient(api_key=…)` (`mini_manus.py:28`) — import triggers network-client init.
- `requirements.txt` pins: `langgraph==0.2.28, langchain==0.3.1, langchain-openai==0.2.1, mem0ai==0.1.6, tavily-python==0.5.0`.
- `Makefile`: `make test` (pytest + cov), `make lint` (flake8 + mypy), `make check` (lint + test), `make format` (black, line-length 100).
- Tests: `tests/__init__.py`, `tests/test_imports.py`, `tests/test_mini_manus.py`; README claims "pytest with mocking for external APIs" and "~85% coverage" (`README.md:86-88`).
- Git: 1 commit (`1cdcceb`, 2025-10-17), branch `main`, remote `git@github.com:nitishagar/diy-manus.git`.

### Current repo is broken as published (all [V] — executed on this machine, 2026-09-19)
- `pip install -r requirements.txt` → `ERROR: ResolutionImpossible`: `mem0ai==0.1.6` requires `langchain-community` that needs `langchain-core<0.3`, while `langchain-openai==0.2.1` needs `langchain-core>=0.3,<0.4`. Both uv and stdlib pip refuse.
- With `mem0ai` unpinned the set installs; then `pytest` fails at **collection**: `openai.OpenAIError: The api_key client option must be set…` — no API keys, no tests.
- With dummy keys, collection still fails: `ValueError: Error: Invalid API key` from mem0's client-side key validation — tests require **real** cloud credentials to even run.
- Environment: Python 3.14.4 (system), venv created fine; `ddgs` and `trafilatura` install and function on 3.14 [V].

### Manus's most important features (official + leaked v1.0 + clones) [R→V spot-checks]
- Agent loop (official blog): user input → model picks action → sandbox executes → observation appended to context → repeat until done; ~50 tool calls per average task; input:output token ratio ~100:1. [R: manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus]
- Planning as todo.md, rewritten and re-stated ("recitation") to counter lost-in-the-middle drift. [R: same]
- File system as externalized context/memory; compress tool outputs but keep restorable pointers (URL/path). [R: same]
- Keep failed actions + errors in context so the model adapts. [R: same]
- "Mask, don't remove" tools; never dynamically add/remove tools mid-task; group prefixes (browser_, shell_). [R: same]
- Leaked v1.0 tool set (29 tools) groups: message (notify/ask), file (read/write/str_replace/find_in_content/find_by_name), shell (exec/view/wait/write_to_process/kill), browser (navigate/click/input/scroll/…), info_search_web, deploy tools, idle. [R: x1xhlol/system-prompts-and-models-of-ai-tools tools.json]
- One tool call per iteration; loop ends via explicit finish/idle/message; session replay UI shows every tool call; runs in a per-session VM sandbox with browser + terminal + file system. [R: Agent loop.txt; manus.im/docs; spectrumailab.com]
- OpenManus (most-starred clone) ships: bash, python_execute, web_search, str_replace_editor, planning, crawl, terminate tools; ReAct loop; optional multi-agent flow; config-driven OpenAI-compatible LLM (works with Qwen). [R: FoundationAgents/OpenManus + app/tool listing]
- OWL (CAMEL-AI) similarly: browser (Playwright), search (DuckDuckGo among backends), code execution (subprocess sandbox), file/terminal toolkits. [R: camel-ai/owl]

### Local stack — verified on this machine [V] unless noted
- ollama 0.21.2 running at 127.0.0.1:11434; models present: `gpt-4o-mini:latest` (actually **qwen3 4B Q4_K_M**, 2.5 GB), `qwen3:4b`, `qwen2.5-coder:1.5b`, `qwen2.5:0.5b` (`/api/tags`).
- OpenAI-compatible endpoint `/v1/chat/completions` works with `openai`-style clients; **tool calling works** with `gpt-4o-mini:latest` — proper `tool_calls` array + `finish_reason:"tool_calls"` [V].
- `reasoning_effort:"none"` on /v1 suppresses the qwen3 `reasoning` field (0-length) and still yields the tool call [V]. Without it, reasoning text can exhaust `max_tokens` before any tool call [V: observed finish_reason "length", empty content].
- CPU speed is the binding constraint: ~4–5 tok/s generation for qwen3-4B on this 4-core i5-7260U (15 GB RAM, no GPU) [V: measured]. qwen2.5:0.5b runs ~21 tok/s but cannot reliably emit tool calls [V: emitted prose instead of tool_calls].
- `tool_choice` is NOT supported on ollama's OpenAI endpoint [R: docs.ollama.com/openai]; models decide on their own.
- Search without keys: `ddgs` (renamed from `duckduckgo_search`) — `DDGS().text(query, max_results=…)` returns list of dicts; verified 3 results on this machine, no key [V]. Rate-limit exceptions exist under load [R: PyPI]. SearXNG via Docker is an alternative but requires container + settings.yml JSON enablement [R: docs].
- Page extraction: `trafilatura` installs and extracts on Python 3.14 here [V]; tops extraction benchmarks vs readability-lxml/newspaper [R: docs].
- Session memory without cloud: mem0 OSS can run fully local but needs `nomic-embed-text` pull + embedded vector store [R: docs.mem0.ai]; SQLite FTS5 is stdlib-only full-text search, enabled in standard Python builds [R: sqlite.org]. No model pull required.
- Browser automation: Playwright `pip install playwright && playwright install chromium`; headless Chromium ~700 MB RAM, ~150–170 MB download [R: playwright.dev, datawookie.dev] — viable but heavyweight for this laptop.
- Docker daemon runs but this user cannot access the socket (`permission denied`) [V] — anything container-based must be optional.
- Network egress works (duckduckgo.com 200) [V]. `gh` CLI 2.46.0 authenticated as nitishagar [V].

## Implicit Spec — invariants any change here must uphold
> Requirements, not designs.
- **Zero-cloud default run**: every runtime path (LLM, search, page fetch, memory, tools) must function with only local resources; no import-time network client construction; missing optional cloud config must never crash startup (the module-level-client failure mode above). Edge: no env vars set.
- **Import must be side-effect free**: importing the package (as tests do) must not construct clients, read secrets, or touch the network. Edge: test collection without any env.
- **Tool-calling loop robustness**: the loop must handle models that return malformed/absent tool calls (parse fallback), and must terminate (max steps / explicit finish) — never loop forever. Edge: unparseable output, tool exception, max-steps reached.
- **Workspace confinement**: file tools resolve paths inside a declared workspace; traversal outside (`..`, absolute, symlink) must be refused. Edge: `../../etc/passwd`, absolute paths.
- **Bounded tool execution**: shell commands run with a timeout and capped captured output; observations re-injected into context are truncated to a size bound (context can grow unbounded otherwise). Edge: hanging process, megabyte stdout.
- **Append-only event context**: each step's messages are appended, never rewritten mid-run (KV-cache-friendly, matches Manus loop); failures stay in context.
- **Deterministic config surface**: exactly one way to point the agent at a different OpenAI-compatible endpoint/model (env), with local defaults; a hosted key changes behavior only via that surface. Edge: wrong URL → clear error, not crash.
- **Session traceability**: every run leaves an inspectable step trace (the "replay" invariant) queryable afterwards.
- **Bounding assumptions**: single-user local machine (no auth/multi-tenancy); CPU-only inference (latency in minutes, not seconds, for multi-step tasks); English/Chinese model output acceptable; shell tool is not a security boundary against the user themselves.

## Workload & Scale Envelope
> Numbers the planner will compute a cost model from. Facts only.
- **Hot operation**: the LLM step call — once per agent iteration; dominant cost = output tokens at ~4–5 tok/s measured [V]. Manus average task ≈ 50 tool calls [R: manus.im blog]; on this CPU that is minutes-to-tens-of-minutes per task, so default max-steps and per-step output caps are load-bearing numbers, not niceties.
- **Data categories**: per-session event log — tens of entries, each observation ≤ a few KB after truncation; sessions DB — hundreds of rows over time (SQLite). Distribution: heavy-tailed tool output sizes (web fetches vs shell one-liners) — truncation decides context growth.
- **Envelope**: current = 1 machine, 1 user, CPU-only, 15 GB RAM, models already on disk (no new pulls required). Target = same (local-first is the product); optional hosted endpoint changes latency only, not architecture.

## Verification Surface
- **Commands** (current repo): test-all `make test` (Makefile:8) · lint `make lint` (flake8 + mypy, Makefile:11) · all `make check` (Makefile:15) · format `make format` (Makefile:19) · **test-one**: `pytest tests/test_mini_manus.py -q` (pytest configured in pyproject `[tool.pytest.ini_options]`). Healthy output: not documented; currently the suite cannot even be collected without real cloud keys [V].
- **Oracles**: none in repo. Available externally: ollama `/api/tags` (is a model served), a scripted FakeLLM returning canned `tool_calls` (buildable — no repo fixture exists), Manus loop description as behavioral oracle (one tool call per iteration, append-only context).
- **Fixtures & harnesses**: none in repo (no conftest, no factories). Tests import the module directly, which is why collection fails without keys.
- **Observability**: agent `print()` statements only (`mini_manus.py:102,142`); no structured trace, no log file.
- **Gaps**: no way to observe the loop's termination behavior; no fixture for a tool-calling LLM; no test for workspace confinement; no end-to-end local smoke (must be built as part of this work — e.g., `make smoke` running one tiny task against local ollama, skipped-with-message if ollama absent).
- **Environment harnesses verified**: ollama 0.21.2 with qwen3-4B serving tool calls [V]; `ddgs` + `trafilatura` on Python 3.14 [V]; docker daemon (root-only socket) [V].

## Hard Cores
- Three independent hard problems: (1) **reliable tool-calling agent loop on small/slow local models** (no tool_choice support, malformed-output fallback, termination, token frugality); (2) **safe local tool execution** (workspace confinement, shell timeout + output capping, path traversal refusal); (3) **all-local service wiring** (ollama client defaults, keyless search, SQLite session memory, optional pieces degrade gracefully offline). Docs/Pages and run-setup are work but not hard cores.

## Evidence Ledger
| Claim | Evidence | Trust | Load-bearing |
|---|---|---|---|
| requirements.txt is ResolutionImpossible | pip + uv runs this session (mem0ai 0.1.6 vs langchain-openai 0.2.1) | V | yes |
| tests fail collection without real cloud keys | pytest collection error after dummy keys | V | yes |
| Clients built at module import | `mini_manus.py:26-28` | V | yes |
| Tool calling works via ollama /v1 with qwen3-4B | curl /v1/chat/completions → tool_calls + finish_reason tool_calls | V | yes |
| reasoning_effort:"none" suppresses reasoning on /v1 | curl run, reasoning len 0, tool call emitted | V | yes |
| CPU gen speed ~4–5 tok/s (qwen3-4B) | timed runs 104.6 s / 442 tok; 112.9 s / 396 tok | V | yes |
| qwen2.5:0.5b cannot reliably emit tool calls | curl run returned prose, tool_calls null | V | yes |
| ddgs keyless search works on Py3.14 | 3 results fetched this session | V | yes |
| trafilatura works on Py3.14 | example.com fetched+extracted | V | yes |
| tool_choice unsupported on ollama /v1 | docs.ollama.com/openai | R | yes |
| Manus loop/todo.md/recitation/tool-mask features | manus.im blog; leaked tools.json | R | yes |
| OpenManus/OWL tool sets | GitHub repos | R | no |
| Playwright headless ~700 MB RAM, 150–170 MB dl | playwright.dev; datawookie.dev | R | no |
| mem0 OSS local needs embedder pull; FTS5 stdlib alternative | docs.mem0.ai; sqlite.org/fts5 | R | no |
| Docker socket not accessible to user | `docker ps` → permission denied | V | yes |

## Architecture Insights
- Manus's own levers (official) are context-engineering ones — append-only events, todo recitation, file-system-as-context, output truncation with restorable pointers — all cheap to implement and precisely what a 4 tok/s CPU budget needs. Applicability: any OpenAI-compatible loop, any model size; validated in production by Manus at scale.
- Small-model tool calling degrades gracefully only if the loop tolerates: missing tool_calls, prose-wrapped JSON, repeated identical calls, and runaways. OpenManus/OWL both wrap this in explicit loop guards (max iterations, terminate tool).
- The OpenAI-compatible `base_url` seam is the single integration point that keeps "local by default, hosted for testing" true without code branches — ollama, OpenAI, Z.ai, vLLM all speak it.

## Historical Context (from thoughts/)
- No prior thoughts/ docs in this repo (created by this research).

## Coverage & Open Questions
- Searched: repo (all files read fully), local environment (models, docker, network, gh), Manus official blog/docs + leaked v1 tools + two major clones, local-stack libraries (ollama docs/issues, ddgs, trafilatura, playwright, mem0/sqlite).
- Bounded: did not benchmark other local models (qwen2.5:3b/7b not on disk; pulling 4.7 GB rejected on disk/time grounds for research phase); did not test Playwright install (heaviest optional piece — planner decides); leaked Manus tool JSON treated as R (repo could change/404).
- Open questions carried to plan: default model choice on this machine; sandbox depth (subprocess + workspace confinement vs Docker-optional); browser tool tier (fetch-only core vs optional Playwright); CLI-only vs web UI for v1.
