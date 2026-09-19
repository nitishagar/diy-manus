# Handoff Ledger — local-first DIY Manus

Append-only resume point. One line per entry with provenance.

## Position
- 2026-09-19: Plan bundle authored (research → spec → plan → validation MINOR-FAIL → fixed in place). Awaiting reviewer PASS confirmation on PLAN_VALIDATION.md before implementation starts (v2.7 rule: no implementation without VERDICT: PASS). Next concrete action: read PASS verdict → begin Phase 1 (Stage A).

## State changes
- 2026-09-19: `.venv/` created in repo (Python 3.14.4) with openai/ddgs/trafilatura/dotenv/pytest installed + verified (research phase). `.venv` must be gitignored (already in .gitignore).
- 2026-09-19: `thoughts/` tree added (research doc, plan bundle, this ledger). No source files changed yet.

## Decisions
- Default model `qwen3:4b` (present on disk here; honest public name for others). `gpt-4o-mini:latest` on this box is an alias of the same qwen3-4B model.
- `reasoning_effort:"none"` sent by default; config can blank it; strip-and-retry on 400 (ollama rejects nothing so far; OpenAI needs "minimal").
- Sessions at `~/.local/share/diy-manus/sessions.db` (home-anchored); workspace default `~/manus_workspace` (home-anchored per validator).
- Runtime deps pinned loose: openai, ddgs, trafilatura, python-dotenv. No langgraph/mem0/tavily (old stack uninstallable — ResolutionImpossible).
- Old `mini_manus.py` + old tests deleted in Phase 1 (not Phase 3) so `make test` can go green; Makefile retargeted same phase.

## Hypotheses
(none yet — implementation not started)

## Confusion
- ollama /v1 sometimes ignores `think:false` on native API but honors `reasoning_effort:"none"` on /v1 (verified 2026-09-19) — quirk of 0.21.2; keep /v1 + reasoning_effort as the seam.

## Open
- Reviewer PASS confirmation (background agent resumed; notification pending).
- GitHub Pages enablement (gh api) — Stage D.
- User-offered API key for hosted-model testing — request at the very end only.
- 2026-09-19: Reviewer confirmed F1–F7 + N1–N9 resolved; PLAN_VALIDATION.md now ends `VERDICT: PASS`. Implementation authorized.
- 2026-09-19 STAGE A COMPLETE: manus/ package (config, llm, util, agent, tools/{base,builtin}), legacy files deleted, Makefile retargeted to .venv-aware PY, requirements rewritten (amendment recorded), pyproject py310. Gates: mypy clean (8 files), flake8 clean, black clean, 22 passed. Next: Stage B (tools: files/shell/search/fetch/browser).
- 2026-09-19 STAGE B COMPLETE: tools/files.py (confinement via resolve+is_relative_to, symlink-safe), tools/shell.py (merged pipe, incremental os.read cap, killpg reaping, start_new_session), tools/search.py (ddgs default, searxng switch, lazy imports), tools/fetch.py (urlopen timeout + trafilatura, http(s)-only), tools/browser.py (lazy playwright, call-time catch-all), default_registry() in tools/__init__. 21 tool tests. Gates: 43 passed, flake8/mypy/black clean. Next: Stage C (session.py, trace.py, __main__.py).
- 2026-09-19 MODEL DECISION (hypotheses worked): live run with qwen3:4b timed out >9.6 min without completing step 1. H1 "tool schemas bloat prompt eval" CONFIRMED (payload 939 tok; prompt eval ~5 tok/s on i5-7260U). H2 "reasoning_effort none ignored with tools on /v1" CONFIRMED (content shows thinking, ollama #17969). /no_think in prompt REFUTED (no effect). think:false via /v1 extra field REFUTED (ignored). Native /api/chat + think:false + 8 tools timed out at 600s. qwen2.5-coder:1.5b REFUTED for tool calling (ignores tools, answers directly, though 12-26s/step). qwen2.5:3b (pulled) CONFIRMED: clean tool_calls, 50s/step, compl 54 tok. Decision: default model qwen2.5:3b; compact SYSTEM_PROMPT + trimmed tool descriptions; qwen3:4b stays documented for stronger machines.
- 2026-09-19 STAGE C COMPLETE (code): session.py (WAL, per-event commit, FTS5, degrade-to-noop), trace.py, __main__.py (dotenv entry-only, --list/--replay, workspace mkdir, exit codes 0/1/2). 62 tests green; flake8/mypy/black clean. Pending: live local run check.
- 2026-09-19 SMOKE HYPOTHESIS: first make smoke FAILED (max_steps). Trace: file_write hello.txt="hi" on step 1 (goal met!), then bye.txt, hello_world.txt — model never calls finish. H: tiny model needs explicit finish discipline. Fix: prompt clause + explicit finish wording in smoke task + max-steps 8 (amendment recorded). Retest pending.
- 2026-09-19 REVIEWS: impl review 7 Important (I1-I7) fixed+confirmed PASS (IMPLEMENTATION_VALIDATION.md); test review 6 gaps fixed PASS 72 tests (TEST_VALIDATION.md); security review PASS w/ 1 High (FIFO unbounded block) + 3 Low, all fixed in 7d13acb (74 tests, smoke re-verified PASS).
- 2026-09-19 PAGES: gh token lacked pages-admin; GITHUB_TOKEN cannot create site first time; POST repos/nitishagar/diy-manus/pages with correct path succeeded → site live at https://nitishagar.github.io/diy-manus/ (HTTP/2 200). Workflow green.
- 2026-09-19 POSITION: all plan phases complete; pushed to main through d09f94b+. Remaining: none in code. User may supply a hosted API key for optional hosted-model test.
