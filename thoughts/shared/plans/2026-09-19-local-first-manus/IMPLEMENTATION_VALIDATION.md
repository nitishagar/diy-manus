<!-- SIGNPOST | 5/5: IMPLEMENTATION_VALIDATION | adversarial review of the implementation | reviewed diff: 1cdcceb..HEAD (20ff216) -->
# Implementation Validation — local-first DIY Manus (2026-09-19)

Reviewer: adversarial re-derivation; did not write the code. Every item defaulted to FAIL until earned with file:line evidence. All probes were executed against the working tree, whose `manus/` files matched HEAD at probe time.

**Review-environment note:** while this review ran, a concurrent writer was modifying `tests/*.py` (uncommitted, additive: +4 tests, warning-assertion on DB degradation, and an in-flight replacement of the live-network fetch test with a localhost HTTP server) and adding `TEST_VALIDATION.md`. Those edits are **not part of the reviewed diff**; HEAD sources were reviewed as committed. No HEAD test was weakened; the uncommitted edits only strengthen.

## Verification performed (independent)

| Check | Result |
|---|---|
| `make lint` (flake8 + mypy) on HEAD | clean (`Success: no issues found in 16 source files`) |
| `black --check manus/ tests/` on HEAD | clean |
| `pytest tests/ -q` on HEAD tree | 62 passed (as planned); 66 with concurrent uncommitted additions; 72 after this review's fixes |
| Probe: `SessionStore.search_text` with FTS MATCH failing on both query forms | **UnboundLocalError raised** (violates session.py's own "reads: empty results on unavailable store" contract) — confirmed at HEAD `session.py:135-151` |
| Probe: `truncate_bytes("A"*1000, 5)` | **returns 1005 bytes** (cap 5, marker 12): `cut` goes negative, `[:cut]` slices from the end — invariant-6 primitive broken for caps < 12 — `util.py:20-22` |
| Probe: agent loop with `call.id=""` | assistant message says `tool_calls[0].id="call_missing"`, following tool message says `tool_call_id="call_1"` — **mismatched pair**; strict OpenAI-compat endpoints 400 the next request — `agent.py:193-205` |
| Probe: live network in unit suite | `test_web_fetch_extracts_text` performed a real HTTPS fetch to example.com (1.77 s) inside the "offline, deterministic" unit suite; `make check` fails on an air-gapped machine, contradicting Desired End State "no cloud … required" |
| Shell kill/reap audit (all exit paths) | EOF-break, timeout, and cap-break all pass through `finally` → `killpg`+`wait(5)`+pipe close (`shell.py:67-71,88-98`); `select`-based deadline cannot deadlock (single merged pipe). PASS |
| Amendment evidence audit | A1 → `HANDOFF_LEDGER.md:34` (first smoke FAIL trace) plausible; A2 → `HANDOFF_LEDGER.md:32` (timed qwen3:4b vs qwen2.5:3b runs) plausible, `config.py:41,61` + `agent.py:23-24` + `smoke.sh:21-22` match the amended text; A3 → verified in commit `4966efb` (requirements rewrite + Makefile retarget + legacy deletion in one Stage A commit) |
| Test-integrity sequencing | `mini_manus.py`, `tests/test_mini_manus.py`, `tests/test_imports.py` deleted in `4966efb` — same commit as the Makefile retarget, exactly as Phase 1 + Amendment 3 require |
| Spec invariant spot-checks | append-only history (`test_history_is_append_only`), one-call-per-iteration, identical-call guard (2 executions then abort), import hygiene on empty env (subprocess test), symlink/traversal refusal, `--replay` round-trip, empty-DB recall — all verified in code + tests |

## Findings

| ID | Severity | Checklist | Finding | Location (HEAD) | Disposition |
|---|---|---|---|---|---|
| I1 | Important | 3, 7 | `search_text` raises `UnboundLocalError` on `rows` when both FTS query forms fail (e.g. corrupted index) — the degrade-to-empty contract of the module docstring is broken on the read path (probe-confirmed) | `manus/session.py:135-151` | **Fixed**: `rows` initialized to `[]` before the probe loop + regression test |
| I2 | Important | 2 (inv 6), 4 | `truncate_bytes` violates its cap when `cap < 12` (marker length): negative `cut` truncates from the end, returning ~the full text. Core bounding primitive; any `MANUS_OBSERVE_CAP_BYTES` < 12 silently disables bounding (probe-confirmed) | `manus/util.py:18-22` | **Fixed**: `cut = max(0, cap - marker_len)` + regression test |
| I3 | Important | 7 | Assistant `tool_calls[].id` ("call_missing") and the paired tool message `tool_call_id` ("call_N") diverge when the model omits a call id (also the path taken by every prose-extracted call). Protocol-invalid conversation; strict endpoints reject the next step with 400 (probe-confirmed) | `manus/agent.py:193-205` | **Fixed**: one fallback id computed per step and used in both messages + regression test |
| I4 | Important | 2 (inv 8) | `--db` is silently ignored by `--list`/`--replay` (they build their store from env only, before overrides are applied), and `Config.from_env()` on those paths can raise uncaught `ConfigError` (e.g. `MANUS_MAX_STEPS=abc` + `--list` → traceback). You cannot inspect a custom-DB run by flag | `manus/__main__.py:126-129` | **Fixed**: config built once via `_apply_overrides` for all paths, `ConfigError` handled everywhere + regression test |
| I5 | Important | 3 | Browser partial-launch leak: `sync_playwright().start()` succeeds, `chromium.launch()` fails (binary missing — the exact case INSTALL_HINT addresses) → the node driver subprocess is never stopped; one leaked driver per failed browser call, up to max-steps per run | `manus/tools/browser.py:23-33` | **Fixed**: `browser.close()`/`playwright.stop()` in an except path on partial launch |
| I6 | Important | 1 (Testing Strategy), 6 | Live-network test in the offline unit suite: `test_web_fetch_extracts_text` fetches `https://example.com`; suite is neither offline nor deterministic and `make check` fails without internet — contradicts plan Testing Strategy ("Unit (offline, deterministic)") and Desired End State (probe-confirmed, 1.77 s live request) | `tests/test_tools.py:199-203` | Fix already in flight **uncommitted** by the concurrent writer (localhost HTTP server). Left untouched to avoid clobbering concurrent work; not re-fixed |
| I7 | Important | 3, 7 | `llm.chat` can still raise past `LLMError`: (a) if the strip-and-retry after a 400 fails again, the retry's exception escapes raw (the mechanism the plan mandates has no typed failure path); (b) `response.choices[0]` → bare `IndexError` on an empty-choices 200. Both escape the CLI's `except LLMError` and crash with a traceback, leaving the run status "running" | `manus/llm.py:66-72, 84` | **Fixed**: retry wrapped → `LLMError`; empty-choices guard → `LLMError` + 2 regression tests |

### Nits (5 reported)

| ID | Nit | Disposition |
|---|---|---|
| N1 | `--model` help text says "default qwen3:4b" — stale after Amendment 2 (actual default `qwen2.5:3b`) | Fixed: `__main__.py:30` |
| N2 | `shell.py` comment claims "drain what select still reports below" but no drain exists; a child writing between the select timeout and `poll()` can lose its tail output (microsecond race, bounded impact) | Fixed comment to state actual behavior; no code change |
| N3 | `test_max_steps_terminates_run` uses shared `/tmp/wsx` + `/tmp/dbx.db` instead of `tmp_path` (unhygienic; collision-prone) | Noted; test files were under concurrent edit — left to that writer |
| N4 | `smoke.sh` passes on any file containing "hi" as a substring (`grep -qi "hi"` matches "this"), though the amended task says content is exactly "hi" | Fixed: `grep -qix "hi"` |
| N5 | `file_list` builds the entire directory listing in memory before truncation (a million-entry dir → unbounded memory); bounded in practice by the user-owned workspace | Accepted, documented here |

Additional nits not individually itemized (count: 6): `_end()` is a trivial pass-through indirection; SearXNG response is read unbounded into memory (user-configured local server — low risk); `SessionStore` never closes its connection explicitly (process-lifetime object; fine for a CLI); `setup.sh --check` can print the missing-venv message twice; `on_event` is not fired for malformed turns, so stderr is silent during prose-only stretches; the LLM call relies on the openai SDK default timeout (600 s × retries) — bounded, but far above the plan's ~50 s/step budget.

## Checklist verdicts

1. **Plan conformance** — PASS with I6. All four stages implemented as specified (loop semantics, tools, sessions/CLI, setup/docs/Pages); all three Amendments' evidence is plausible and present in HANDOFF_LEDGER; no amendment touching mechanism/interface/data-shape/ordering/locking/cost is mislabeled `factual` (A3 moves commit-time file placement only, not runtime ordering; A2 changes a config default and payload size, both factual corrections of the environment premise).
2. **Spec invariants** — upheld, with I1 (invariant 9/7 read-path), I2 (invariant 6), I3 (invariant 4 protocol shape), I4 (invariant 8 seam consistency) as localized defects, all fixed. Zero-cloud default, import hygiene, termination (max-steps/3-strike/loop-guard/tool timeouts), workspace confinement, append-only, traceability, recall, minimal deps: verified in code and tests.
3. **Failure/concurrency** — shell process-group kill + pipe close on every exit path verified; per-event commits verified; DB degradation verified except I1 (fixed); playwright leak I5 (fixed); LLM typed-error gaps I7 (fixed).
4. **Cost model** — no hidden N+1; observations double-bounded (tool-level cap + agent-level truncate); message history bounded by max-steps × cap (matches the 300 KB large-task figure); FTS rows capped at 8; stored args/observations clipped (2 KB / 20 KB). N5 is the only unbounded-in-memory edge.
5. **Anti-pattern sweep** — clean. No DI framework, no retry library, no caching layer, env-only config, no hand-rolled crypto; JSON scanning in `util.py` is a justified small-model recovery helper with string-aware brace tracking. `_end()` indirection and `_state` browser retention are the only flags, both defensible (documented in-code).
6. **Test integrity** — PASS. Legacy deletion + Makefile retarget sequenced in one Stage A commit per plan/amendment; no HEAD test weakened; in-flight concurrent edits only add coverage.
7. **Common defects** — I1, I2, I3, I7 (all fixed). Tool error observations are the designed failure style and are correctly used (`_execute` catch-all); no swallowed exceptions outside the designed degradation wrappers.
8. **Convention fit** — PASS. flake8, mypy, black clean at HEAD and after fixes; final suite 72 passed.

## Fixes applied by this review (uncommitted working-tree changes)

- `manus/session.py` — I1; `manus/util.py` — I2; `manus/agent.py` — I3; `manus/__main__.py` — I4 + N1; `manus/tools/browser.py` — I5; `manus/llm.py` — I7; `manus/tools/shell.py` — N2 (comment); `scripts/smoke.sh` — N4.
- `tests/test_regressions.py` (new) — 6 tests pinning I1, I2, I3, I4, I7.
- Post-fix gates: flake8 clean, mypy clean (16 files), black clean, **72 passed**.

The reviewed diff as committed earns MINOR-FAIL: seven localized defects, none architectural; all but I6 (owned by the concurrent in-flight fix) repaired in place and regression-tested.

VERDICT: MINOR-FAIL
