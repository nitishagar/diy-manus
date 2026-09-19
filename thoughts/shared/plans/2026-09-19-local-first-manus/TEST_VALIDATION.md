<!-- SIGNPOST | 5/5: TEST_VALIDATION | adversarial review of tests against IMPLICIT_SPEC + PLAN | done 2026-09-19 -->
# Test Validation — local-first DIY Manus

Reviewer: adversarial test reviewer (did not write the tests). Suite at review time: 62 tests, all passing.
Method: checklist review against IMPLICIT_SPEC invariants 1–11 + PLAN.md Phase 1–3 success criteria, plus
**mutation testing** (inject the regression each test claims to guard against; a surviving mutation = the test
is not actually guarding anything).

## Summary

The suite is substantially stronger than a happy-path suite: the FakeLLM oracle drives the real agent loop,
termination/guards/append-only are asserted on recorded message history, confinement includes symlink escape,
shell cap/timeout/reaping use real subprocesses with bounded sleeps, session tests use real SQLite across
connections, and there are no skips/xfails/tautological-only asserts. Legacy `mini_manus.py` /
`test_mini_manus.py` / `test_imports.py` deletion is plan-sanctioned (PLAN Phase 1 "Files removed"; commit
`4966efb`). Four real gaps were found and **each was confirmed by a surviving mutation before being fixed**
(details below). All fixes were applied in this review; suite is now 66 passing, flake8 clean, `make check` green.

## Findings

### Important

- **I1. Agent-level tool-crash degradation was completely untested** (invariant 7 / partial-failure edge:
  "tool failures are observations, never loop crashes"). Mutation proof: deleting the `try/except` in
  `Agent._execute` (manus/agent.py:187-191) passed all 62 tests — no test exercised a tool whose `run` raises.
  **Fixed:** `tests/test_agent.py::test_tool_exception_becomes_observation_and_loop_continues` asserts the run
  finishes, and the `Tool error … disk on fire` observation is in the final context. Mutation now killed.

- **I2. Import-hygiene test guarded only 8 of 16 modules and asserted almost nothing** (invariant 2). It never
  imported `manus.session`, `manus.trace`, `manus.__main__`, and its only content assertion was the tautology
  `assert openai.OpenAI is not None`. Mutation proof: adding a filesystem write (mkdir) at import time to
  `manus/session.py` passed the whole suite. (Tool modules were transitively covered via `manus.tools`; a
  module-level client there *was* caught — but only because it raises on empty env, not because it was asserted.)
  **Fixed:** `tests/test_llm.py::test_import_hygiene_no_side_effects_on_empty_env` now imports **every** manus
  module under a `sys.addaudithook` that fails on any network event (socket/urllib), subprocess spawn, or
  filesystem write during import; also asserts lazy optional deps (`ddgs`/`trafilatura`/`playwright`) are not
  pulled in at module load. Both mutations now killed.

- **I3. The "offline" suite performed a real external network fetch.** `test_web_fetch_extracts_text` fetched
  `https://example.com` — the only non-hermetic test in a suite whose `make test` is documented offline
  (no ollama); it fails on an air-gapped/CI machine and trusts a third-party page's uptime. **Fixed:** the test
  now serves a fixed HTML page from a localhost `HTTPServer` (ephemeral port, shutdown in `finally`) and asserts
  real trafilatura extraction of that content.

- **I4. The single-config-seam had two untested halves** (invariant 8): nothing verified that `MANUS_BASE_URL`
  actually reaches the SDK client (the mechanism by which a hosted endpoint is ever used), and nothing pinned
  that defaults are local. **Fixed:** `tests/test_llm.py::test_env_base_url_override_flows_to_client` (env
  override → captured `base_url` on the fake SDK client) and
  `tests/test_cli.py::test_config_defaults_are_local` (zero env → `127.0.0.1:11434/v1`, key `ollama`, local
  workspace).

- **I5. Invalid-JSON-arguments 3-strike abort path untested** (invariant 3 edge). Only recover-after-one-bad-call
  was covered; the abort branch of the `args is None` path had no test. **Fixed:**
  `test_three_invalid_json_arguments_abort` (3 malformed-arguments calls → `aborted_malformed`, steps == 3).

- **I6. DB-unavailable degradation asserted only no-raise/no-op** (invariant 9: "trace loss is **reported**").
  The warning emitted by `SessionStore._warn` was never asserted. **Fixed:** `test_unwritable_db_degrades_…`
  now also asserts the `warning: session store unavailable` line on stderr.

### Nits (4; not fixed)

1. SearXNG backend has no failure-path test (only the success path is mocked); its failure shares the
   `except` already covered via the ddgs backend, so severity is low.
2. `test_max_steps_terminates_run` hardcodes `workspace="/tmp/wsx"`, `db_path="/tmp/dbx.db"` instead of a
   tmp-path fixture (no pollution occurs today because the loop tools never touch those paths, but it is
   brittle by construction).
3. `test_roundtrip_search_finds_events` asserts the weak token `"run" in hits` next to the meaningful
   `"kubernetes"` check; the first half alone would pass on unrelated output.
4. "No dynamic tool-list mutation mid-run" (invariant 7) is only covered statically
   (`test_default_registry_fixed_and_wellformed`); no test observes the registry across a full run.

## Checklist results (post-fix state)

1. **Invariant coverage** — PASS after I1–I6. Zero-cloud default (hermetic suite + local-defaults pin);
   import side-effect-free (all 16 modules + audit hook); loop termination incl. prose-fallback, 3-strike
   aborts (prose / bad-JSON / unknown-tool), identical-call guard + negative case, max-steps, shell
   timeout+reaping; one-tool-per-iteration + append-only (deep-copied per-call history, prefix assertion);
   confinement incl. `..`, absolute, and symlink escape (read *and* write, outside file verified untouched);
   bounded execution (shell cap with kill notice, tool- and agent-level truncation markers, unicode boundary,
   empty output); graceful degradation (browser missing at import *and* call time, search failure → observation,
   tool crash → observation, DB unavailable → warning); config seam (env overrides incl. base_url propagation,
   local defaults); crash-readable trace (cross-connection read with column assertions); FTS5 probe + recall
   round-trip + empty-DB "no history".
2. **Criteria coverage** — PASS. Every Phase 1–3 Local/End-to-end criterion maps to named tests, including the
   previously overstated "importing every manus module" hygiene claim. (Phase 3's live-model manual criterion
   is out of test scope by plan; Phase 4 `make smoke` is the ollama-bearing check.)
3. **Real assertions** — PASS. Outcomes asserted (statuses, step counts, history contents, DB rows, exit codes,
   stderr text). The one prior tautology was removed with I2.
4. **Test integrity** — PASS. Legacy deletion plan-sanctioned; no skips/xfails/marks added or found; my
   changes only add/strengthen. (3 pre-existing mypy arg-type warnings in test_session.py are outside
   `make lint`'s mypy scope (manus/ only) and predate this review.)
5. **Over-mocking** — PASS. FakeLLM sits at the LLM seam while the real loop, registry, session store, and
   file/shell tools run for real; search/fetch/browser mocks sit at dependency boundaries; CLI tests mock
   `Agent` but verify the CLI's own wiring (store rows, exit codes, replay output), with the agent covered
   by its own suite.
6. **Determinism** — PASS after I3. No external network remains in the unit suite; shell-timeout test uses a
   bounded real ~3s sleep and a unique `pgrep` marker (negligible SIGKILL-delivery race); searxng/ddgs/browser
   are mocked; `make check` = 66 passed, ~5s.

## Changed in this review

`tests/test_agent.py` (+2 tests, 1 tool fixture), `tests/test_llm.py` (hygiene hardening, +1 base_url test),
`tests/test_tools.py` (localhost fetch server), `tests/test_session.py` (warning assertion), `tests/test_cli.py`
(+1 local-defaults test). No source under `manus/` was modified.

VERDICT: PASS
