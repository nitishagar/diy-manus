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
