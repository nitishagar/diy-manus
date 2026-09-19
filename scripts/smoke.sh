#!/usr/bin/env bash
# End-to-end local smoke test: one tiny real task against the local LLM.
# Prints SMOKE PASS / SMOKE SKIP / SMOKE FAIL and exits 0/0/1 respectively.
set -uo pipefail

cd "$(dirname "$0")/.."
MODEL="${MANUS_MODEL:-qwen2.5:3b}"
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
PY=".venv/bin/python3"
[ -x "$PY" ] || PY=python3

if ! curl -s --max-time 3 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  echo "SMOKE SKIP: ollama not reachable at $OLLAMA_HOST (start it with: ollama serve)"
  exit 0
fi

SMOKE_DIR="$(mktemp -d /tmp/diy-manus-smoke.XXXXXX)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

echo "· running task in $SMOKE_DIR (this can take a few minutes on CPU)..."
"$PY" -m manus "Create a file named hello.txt whose content is exactly: hi. Then call finish." \
  --workspace "$SMOKE_DIR" --db "$SMOKE_DIR/sessions.db" --max-steps 8 \
  >"$SMOKE_DIR/stdout.log" 2>"$SMOKE_DIR/stderr.log"
STATUS=$?

if [ "$STATUS" -eq 0 ] && [ -f "$SMOKE_DIR/hello.txt" ] && grep -qix "hi" "$SMOKE_DIR/hello.txt"; then
  echo "SMOKE PASS: task finished and hello.txt created"
  exit 0
fi

echo "SMOKE FAIL: exit=$STATUS (model: $MODEL)"
echo "--- stderr tail ---"
tail -5 "$SMOKE_DIR/stderr.log"
exit 1
