<!-- SIGNPOST | 3/5: PLAN_VALIDATION | adversarial review of PLAN.md | Next: implement+review -->
# Plan Validation — Local-first DIY Manus (2026-09-19)

Validator: adversarial re-derivation, scale medium. Inputs read fully: PLAN.md, IMPLICIT_SPEC.md, research doc, plus repo (`mini_manus.py`, `Makefile`, `pyproject.toml`, `tests/`, `requirements*.txt`, `.env.example`, `.flake8`, `README.md`). Every item defaulted to FAIL until earned.

## Verification performed (independent, this session)

| Check | Result |
|---|---|
| Reproduce legacy-suite collection failure | `.venv/bin/python -m pytest --collect-only -q` → `ERROR tests/test_mini_manus.py - openai.OpenAIError: The api_key client option must be set…`, "1 error during collection" — confirms `make test` cannot pass while legacy tests exist |
| Callers of `mini_manus.py` (blast radius) | grep: `Makefile` (lines 17 flake8, 19 mypy, 22 black), `README.md` (lines 24, 77), the two test files — the plan's original "no other consumers" claim was false |
| ollama endpoint + default model | `curl 127.0.0.1:11434/api/tags` → up; `qwen3:4b` present (plan's default model exists) |
| .venv deps on Python 3.14.4 | `pip list`: openai 1.109.1, ddgs 9.16.0, trafilatura 2.2.0, python-dotenv 1.0.1, pytest 7.4.3, flake8 6.1.0, mypy 1.7.1 — plan's "verified installable on 3.14" claim holds (research named only ddgs/trafilatura) |
| FTS5 availability | `CREATE VIRTUAL TABLE … USING fts5` in-memory → OK (plan's probe-test approach is sound) |
| `trafilatura.fetch_url` timeout | signature `(url, no_ssl, config, options)` — **no timeout parameter**; bears on invariant 3 |
| `ddgs` timeout | `timeout` is a `DDGS.__init__` kwarg (default 5s), not a `.text()` kwarg (ddgs.py:49) |
| `gh` auth + Pages state | authenticated as nitishagar; `GET repos/nitishagar/pages` → 404 (Pages not yet enabled — Phase 4 step is real work) |
| Repo state | git @ `1cdcceb` on main, matches plan's Current State |
| Plan file:line citations | `mini_manus.py:26-28` module-level clients ✓; `make test/lint/check/format` targets exist in Makefile ✓; pytest config at `pyproject.toml:15-19` ✓ |

## Checklist re-derivation

| # | Item | Verdict | Basis |
|---|---|---|---|
| 1 | Every invariant has a named mechanism | FAIL → fixed | All 11 invariants map to mechanisms, but invariant 3 named a timeout only for shell; search/fetch had none (verified `trafilatura.fetch_url` has no timeout param) → `net_timeout_s` added |
| 2 | Retry/partial-failure/concurrency handled; no state leaks | FAIL → fixed | Strip-and-retry, killpg+reap, `finally` pipe close, DB degradation all named; but "incremental stdout+stderr read" hand-waved the classic two-pipe deadlock → single merged pipe + wall-clock deadline specified |
| 3 | All callers enumerated, file:line, back-compat | FAIL → fixed | "No other consumers" was false: `Makefile:17/19/22` (and `README.md:24/77`) consume the deleted file; now enumerated; Makefile retarget moved into the deletion phase |
| 4 | No correctness traded for "simpler" | PASS (after fixes) | Remaining "simpler" choices (plain-list registry, env-only config, stdlib JSON) carry no correctness cost |
| 5 | No unjustified new pattern | PASS | openai-SDK-over-httpx, FTS5-over-mem0, dotenv reuse all justified with present needs; anti-DI/no-cache guardrails explicit |
| 6 | No TBDs in plan; no mechanisms in spec | PASS | Scanned both: no TBDs; recall Stage-C placeholder is a defined mechanism, not a TBD; spec stays requirement-level |
| 7 | Success criteria dense; invariant→failing-criterion mapping; cited commands exist; research Gaps closed | FAIL → fixed | Phase Local+E2E criteria present and specific; BUT (a) agent-level observation truncation (named mechanism) had no failing test — tool-level caps don't cover recall/search aggregates; (b) Phase 1/2 E2E criteria (`make test`) were unsatisfiable while legacy tests exist; (c) network-tool timeout had no test. All three closed. Commands verified to exist; research Gaps (FakeLLM fixture, confinement tests, termination observability, local smoke) each closed by a named harness |
| 8 | Anti-pattern sweep | PASS | No DI, no crypto, retained state = sessions DB only, per-event commits justified (crash-readable invariant), single-threaded + WAL adequate, every config knob (reasoning_effort, search backend) has a named present need |
| 9 | Decomposition | PASS (after fix) | Four stages each own one hard core, dependency-ordered; but Stage A/D criteria were unsatisfiable as sequenced (legacy deletion in Stage C) — repaired by moving removal to Stage A |
| 10 | Defect fixes have failing-first tests | N/A | Replacement project, not defect-fix; the loop-oracle FakeLLM suite serves as the first gate |
| 11 | Intent OQs answered/recorded | PASS | OQ1→`qwen3:4b` default (model verified present); OQ2→confinement+timeouts, Docker roadmap (socket permission verified); OQ3→CLI+replay, web UI roadmap; OQ4→fetch core + optional Playwright with call-time degradation |
| 12 | Stranger-implementable | FAIL → fixed | Smoke task text was unspecified ("tiny 4-step task"); deletion/Makefile ordering forced improvisation; no commit/push step though Desired End State requires pushed repo. All named now |

## Findings

| ID | Severity | Checklist | Finding | Location | Disposition |
|---|---|---|---|---|---|
| F1 | Important | 7, 9 | Phase 1/2 End-to-end criteria require `make test` (full suite) green, but legacy `tests/test_mini_manus.py` + `tests/test_imports.py` are deleted only in Phase 3; the legacy suite fails at collection without cloud keys (reproduced: `openai.OpenAIError` at collection) and its pins are uninstallable — the criterion is unsatisfiable as sequenced | PLAN.md Phase 1/2 criteria (old lines 65, 83); Phase 3 "Files removed" (old lines 95–96) | Fixed: removal + Makefile retarget moved to Phase 1 |
| F2 | Important | 3 | Blast radius claimed deleted files "have no other consumers in repo" — false. `Makefile:17` (`flake8 mini_manus.py tests/`), `Makefile:19` (`mypy mini_manus.py`), `Makefile:22` (`black mini_manus.py tests/`) break `make lint`/`make check` the moment `mini_manus.py` is deleted, breaking Phase 3's own E2E criterion until Phase 4 | PLAN.md Blast radius (old line 28); Makefile:17,19,22 | Fixed: callers enumerated; retarget scheduled in the deletion phase |
| F3 | Important | 2, 4 | Shell "incremental stdout+stderr read" on two unmerged pipes can deadlock (child blocked writing a full stderr pipe while the read loop waits on stdout; a pre-`wait` read loop never reaches the timeout). Plan already merges output in the observation, so the deadlock-free form is free | PLAN.md Phase 2 `shell.py` (old line 74) | Fixed: `stderr=subprocess.STDOUT`, single pipe, wall-clock deadline, `finally` close |
| F4 | Important | 1 | Spec boundary "workspace path that does not exist (created, with parent creation)" had no named mechanism for the workspace root itself: `file_write` creates parents under the root, but shell `Popen(cwd=<missing>)` raises and nothing creates the root at run start | Spec Boundary inputs; PLAN.md Phase 3 `__main__.py` | Fixed: workspace auto-create (parents included) at run start + criterion |
| F5 | Important | 7 | Agent-level observation truncation per `observe_cap_bytes` (named in Approach) had no criterion that fails if absent — Phase 2's cap/marker tests only exercise tool-level bounds; recall/search aggregate outputs rely on the agent-level truncation, so invariant 6 could be violated undetected | PLAN.md Approach + Phase 1 criteria | Fixed: Phase 1 FakeLLM oversized-observation truncation test added |
| F6 | Important | 1, 7 | Invariant 3 says "every tool execution has a timeout" but only shell named one. Verified: `trafilatura.fetch_url` has no timeout parameter (2.2.0); `ddgs` timeout is constructor-only; a hung network call blocks the loop indefinitely with no failing test | PLAN.md Phase 2 search/fetch; research invariant 3 | Fixed: `net_timeout_s` (30) in config; `DDGS(timeout=…)`, `urlopen(timeout=…)`+`trafilatura.extract`; mocked timeout/hang tests |
| F7 | Important | 2, 7 | Session DB parent directory (`~/.local/share/diy-manus/`) creation was not named. On a fresh machine `sqlite3.connect` fails, the degrade-to-noop path fires on **every** run, and traces silently never persist — invariant 9 defeated by the happy path, not the error path | PLAN.md Phase 3 `session.py` | Fixed: mkdir parent before connect; fresh-DB-creation criterion added |

## Nits (5 reported)

| ID | Nit | Disposition |
|---|---|---|
| N1 | Smoke task underspecified ("tiny 4-step task" — no task text, no produced-file assertion); a stranger must invent the contract the criterion checks | Fixed: named `create hello.txt containing hi`, `--max-steps 4`, asserts `hello.txt` in SMOKE_DIR |
| N2 | No commit/push step anywhere though Desired End State requires "all pushed to GitHub"; the no-co-author-attribution user constraint was not restated | Fixed: one sentence added to Phase 4 Pages section |
| N3 | Invariant 2's criterion ("tests import package on empty env") only fails for key-requiring construction; module-level clients with local defaults would pass silently | Fixed: explicit import-hygiene test (zero clients constructed importing all modules on empty env) |
| N4 | Empty-DB `recall` → "no history" edge (invariant 10) not in any criterion bullet | Fixed: added to Phase 3 criteria + Testing Strategy |
| N5 | `pyproject.toml` pins black `target-version py39` / mypy `python_version 3.9` while the plan declares a ≥3.10 package floor | Fixed: plan now says mypy `python_version` raised 3.9→3.10 |

Additional nits not individually itemized (count: 4): research doc's Verification Surface line-cites are off by a few lines (Makefile "test" is line 12, not 8 — plan does not inherit the numbers); `step_max_tokens=512` can truncate long tool-call arguments into a "malformed" strike (envelope-consistent; worth a README note); the identical-call guard needs sorted-key canonicalization of args JSON ("canonical args" implies but does not state it); no row cap named for `recall` output (bounded in practice by the agent-level cap once F5's test exists).

## Verdict rationale

Seven Important findings, all localized sequencing/specification defects — none invalidates the architecture (OpenAI-compatible seam, one-call loop with guards, fixed tool registry, SQLite+FTS5, staged A→D) or requires rework of a hard core. Every finding was repaired by a minimal in-place edit to PLAN.md (listed above); the research doc and spec required no changes. Post-fix, all twelve checklist items pass or are N/A.

VERDICT: MINOR-FAIL

## Re-validation (2026-09-19, post-fix)

PLAN.md re-read after the fix pass. F1–F7 verified in the updated text: Phase 1 now carries "Files removed (this phase)" + "`Makefile` (retargeted this phase)" and Phase 3's removal section is gone (F1/F2); shell tool specifies `stderr=subprocess.STDOUT`, a single merged pipe, wall-clock deadline, `finally` close (F3); `__main__` creates the workspace root with parents, with a matching Phase 3 criterion (F4); agent-level truncation test present in Phase 1 criteria, Design Analysis invariant 6, and Testing Strategy (F5); `net_timeout_s` wired through config, search (`DDGS(timeout=…)`), fetch (`urlopen(timeout=…)`), invariant 3, Phase 2 criteria, and Testing Strategy (F6); session DB parent-directory creation + fresh-DB criterion present (F7). Nits verified: N1 smoke task literal with produced-file assertion; N2 commit/push + no-co-author sentence; N3 import-hygiene test; N4 empty-DB recall edge in criteria + Testing Strategy; N5 mypy `python_version` 3.9→3.10. Residual summarized nits closed with two one-clause edits: sorted-key canonicalization named for the identical-call guard (former S3) and a README limits note for `step_max_tokens` truncation + 10 KB observation cap (former S2); former S1 (research-doc line cites) required no plan change — the plan cites no inherited line numbers; former S4 (recall row cap) resolved via the invariant-6 agent-level cap mechanism and its new test.

All 7 Important findings and 9 nits resolved.

VERDICT: PASS
