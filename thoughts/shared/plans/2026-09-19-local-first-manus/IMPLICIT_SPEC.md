<!-- SIGNPOST | 1/5: SPEC | requirements only, no designs | Next: PLAN.md
     Pipeline: SPEC -> PLAN -> PLAN_VALIDATION -> implement+review -> tests+TEST_VALIDATION -> green -->
# Implicit Spec — local-first DIY Manus

Derived from `thoughts/shared/research/2026-09-19-local-first-manus.md`. Requirements only; mechanisms belong to PLAN.md.

## Invariants (any change in this repo must uphold)

1. **Zero-cloud default run** — Every runtime path (LLM, search, page fetch, session memory) functions with local resources only: a local OpenAI-compatible endpoint for the LLM, keyless search, stdlib storage. No code path may require a cloud API key to start. Edge: fresh machine, no env vars set → agent still starts (may report search/network failures gracefully mid-task, never at startup).
2. **Import is side-effect free** — Importing any package module constructs no network clients, validates no API keys, reads no secrets, touches no network. Edge: pytest collection on a machine with zero env config must succeed.
3. **Loop terminates, always** — The agent loop ends on: explicit finish, max-steps reached, or unrecoverable repeated malformed model output. A run never blocks indefinitely; every tool execution has a timeout. Edge: model returns prose forever; model returns the same tool call forever (no progress guard); shell command hangs.
4. **One tool call per iteration, append-only context** — Each iteration executes at most one tool call and appends its observation; earlier messages are never rewritten or removed mid-run; failed tool calls and their errors remain in context. Edge: model requests multiple tool calls in one response.
5. **Workspace confinement for file tools** — File tools resolve all paths against the declared workspace and refuse anything that escapes it (absolute paths outside, `..` traversal, symlink escape). Edge: `../../etc/passwd`, absolute path, symlink pointing outside.
6. **Bounded tool execution and observations** — Shell runs with a timeout and capped stdout/stderr; every observation re-injected into context is truncated to a documented size bound; truncation is marked in the observation text. Edge: megabyte stdout; hanging process.
7. **Optional capability degrades gracefully** — Capabilities whose optional deps are missing (Playwright browser, SearXNG backend) are always exposed as tools but return a structured, actionable "unavailable" observation rather than crashing; no dynamic tool-list mutation mid-run. Edge: playwright not installed; SearXNG URL unreachable.
8. **Single config seam, local defaults** — Exactly one env-driven config surface controls endpoint/model/limits; defaults are local (ollama endpoint, local model, local workspace). A hosted endpoint is used only by changing that surface, never by code branches. Edge: unreachable endpoint → clear, actionable error at first use.
9. **Session traceability** — Every run persists a step-level trace (iteration, tool, args, observation, timing) and a final result to local storage, queryable afterwards from the CLI ("replay"). Edge: DB unavailable → run proceeds with warning, trace loss is reported, run never crashes.
10. **Cross-session memory without cloud** — Past runs are searchable from the agent (a recall tool) using local full-text search over persisted traces. Edge: empty DB → tool returns "no history" observation.
11. **No silent scope creep in deps** — Runtime deps stay minimal and verified on the target Python (3.14); a dep is added only if a spec invariant demands it.

## Concurrency / partial-failure edges
- Shell tool must reap timed-out processes (no orphaned children holding the pipe).
- Session DB writes are short-lived and per-run; a crashed run must leave a readable trace up to the crash point.
- Search backend failure yields an error observation into the loop (task continues), not an exception out of the loop.

## Boundary / degenerate inputs
- Empty task string; empty tool output; unicode-heavy content; very long single-line output; workspace path that does not exist (created, with parent creation); DB path unwritable.

## Bounding assumptions (confirmed for this work)
- Single-user local machine: no auth, no multi-tenancy, no concurrent agent runs on one workspace.
- Shell tool is a convenience, not a security boundary against the machine's own user; confinement is enforced for file tools, and shell runs inside the workspace directory — hostile-prompt-injection-driven shell use is documented as a known risk in the README, not solved by sandboxing in v1.
- CPU-only inference (~4–5 tok/s): default max-steps and per-step output caps are tuned for minute-scale, not second-scale, runs.
- English-language tasks; CLI UX for v1; web UI is roadmap, not scope.

## Intent open questions — carried checklist
- [ ] OQ1 default local model → answer in PLAN (candidate: `qwen3:4b`, already on disk).
- [ ] OQ2 sandbox depth → answer in PLAN (candidate: workspace confinement + timeouts; Docker documented as roadmap because user lacks docker socket permission).
- [ ] OQ3 web UI vs CLI v1 → answer in PLAN (candidate: CLI trace + replay; web UI roadmap).
- [ ] OQ4 browser capability tier → answer in PLAN (candidate: HTTP fetch core; Playwright optional with graceful degradation).
