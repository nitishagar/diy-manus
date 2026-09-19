#!/usr/bin/env bash
# One-command local setup for diy-manus. Idempotent.
#   bash scripts/setup.sh [--check] [--with-browser]
# --check        verify only, change nothing
# --with-browser also install Playwright Chromium (optional browser tools)
set -uo pipefail

cd "$(dirname "$0")/.."
CHECK=0
BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --with-browser) BROWSER=1 ;;
    *) echo "unknown option: $arg"; exit 1 ;;
  esac
done

MODEL="${MANUS_MODEL:-qwen2.5:3b}"
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
FAIL=0

ok()   { printf '  \033[32mOK\033[0m      %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mMISSING\033[0m %s\n' "$1"; FAIL=1; }

echo "diy-manus local setup (model: $MODEL)"

# 1. Python venv + dependencies
if [ ! -x .venv/bin/python3 ]; then
  if [ "$CHECK" -eq 1 ]; then
    bad "python venv (.venv) — run: bash scripts/setup.sh"
  else
    echo "· creating venv..."
    python3 -m venv .venv || bad "could not create venv (is python3 installed?)"
  fi
fi
if [ -x .venv/bin/python3 ]; then
  if ! .venv/bin/python3 -c "import manus" >/dev/null 2>&1 || \
     ! .venv/bin/python3 -c "import openai, ddgs, trafilatura, dotenv" >/dev/null 2>&1; then
    if [ "$CHECK" -eq 1 ]; then
      bad "python dependencies — run: bash scripts/setup.sh"
    else
      echo "· installing dependencies..."
      .venv/bin/python3 -m pip install -q --upgrade pip
      .venv/bin/python3 -m pip install -q -r requirements-dev.txt || bad "dependency install failed"
    fi
  fi
  if .venv/bin/python3 -c "import openai, ddgs, trafilatura, dotenv" >/dev/null 2>&1; then
    ok "python venv + dependencies"
  fi
else
  bad "python venv (.venv)"
fi

# 2. ollama reachable
if curl -s --max-time 3 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  ok "ollama reachable at $OLLAMA_HOST"
else
  bad "ollama not reachable at $OLLAMA_HOST — start it with: ollama serve"
fi

# 3. model present
if curl -s --max-time 5 "$OLLAMA_HOST/api/tags" | grep -q "\"name\":\"$MODEL\""; then
  ok "model $MODEL available"
else
  if [ "$CHECK" -eq 1 ]; then
    bad "model $MODEL — run: ollama pull $MODEL"
  else
    echo "· pulling $MODEL (one-time download)..."
    ollama pull "$MODEL" && ok "model $MODEL pulled" || bad "ollama pull $MODEL failed"
  fi
fi

# 4. optional browser tooling
if [ "$BROWSER" -eq 1 ] && [ "$CHECK" -eq 0 ]; then
  echo "· installing Playwright Chromium (optional browser tools)..."
  .venv/bin/python3 -m pip install -q playwright && .venv/bin/python3 -m playwright install chromium \
    && ok "playwright chromium" || warn "playwright install failed; browser tools stay unavailable (harmless)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "Setup verified. Try: make run TASK='create hello.txt containing hi'"
  exit 0
fi
echo "Some items are missing. Re-run: bash scripts/setup.sh"
exit 1
