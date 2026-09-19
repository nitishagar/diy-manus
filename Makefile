PY := $(shell if [ -x .venv/bin/python3 ]; then echo .venv/bin/python3; else echo python3; fi)

.PHONY: help install test lint format check clean run smoke setup

help:  ## Show this help message
	@echo "DIY Manus — local-first agent. Dev commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies into the venv
	$(PY) -m pip install -r requirements-dev.txt

test:  ## Run unit tests (offline, no ollama needed)
	$(PY) -m pytest tests/ -v --cov=manus --cov-report=term-missing

lint:  ## Run linting checks
	@echo "Running flake8..."
	$(PY) -m flake8 manus/ tests/
	@echo "Running mypy..."
	$(PY) -m mypy manus/

format:  ## Format code with black
	$(PY) -m black manus/ tests/

check: lint test  ## Run all checks (lint + test)

clean:  ## Clean up cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov/

run:  ## Run a task locally: make run TASK="create hello.txt containing hi"
	$(PY) -m manus "$(TASK)"

smoke:  ## End-to-end local smoke test (needs local ollama)
	bash scripts/smoke.sh

setup:  ## One-command local setup (venv, deps, ollama check)
	bash scripts/setup.sh
