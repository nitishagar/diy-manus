.PHONY: install test lint format check clean help

help:  ## Show this help message
	@echo "Mini-Manus Development Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

test:  ## Run unit tests
	pytest tests/ -v --cov=. --cov-report=term-missing

lint:  ## Run linting checks
	@echo "Running flake8..."
	flake8 mini_manus.py tests/
	@echo "Running mypy..."
	mypy mini_manus.py --ignore-missing-imports

format:  ## Format code with black
	black mini_manus.py tests/

check: lint test  ## Run all checks (lint + test)

clean:  ## Clean up cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov/

dev-setup: install  ## Setup development environment
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. cp .env.example .env"
	@echo "  2. Add your API keys to .env"
	@echo "  3. Run 'make check' to verify setup"
