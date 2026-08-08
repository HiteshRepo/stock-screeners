VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

.DEFAULT_GOAL := help

.PHONY: help venv install install-ai-anthropic install-ai-openai install-ai-all \
        test test-v coverage lint fmt check clean cache-clear

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Setup"
	@echo "  venv                  Create .venv"
	@echo "  install               Install package + dev deps into .venv"
	@echo "  install-ai-anthropic  Also install anthropic SDK"
	@echo "  install-ai-openai     Also install openai SDK"
	@echo "  install-ai-all        Install both AI SDKs"
	@echo ""
	@echo "Dev"
	@echo "  test                  Run pytest (quiet)"
	@echo "  test-v                Run pytest (verbose)"
	@echo "  coverage              Run pytest with coverage report"
	@echo "  lint                  Run ruff linter"
	@echo "  fmt                   Auto-format with ruff"
	@echo "  check                 lint + test (CI gate)"
	@echo ""
	@echo "Ops"
	@echo "  cache-clear           Delete .cache/market_data.json"
	@echo "  clean                 Remove .venv, __pycache__, .egg-info"

# ── Setup ────────────────────────────────────────────────────────────────────

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e .
	$(PIP) install -r requirements-dev.txt

install-ai-anthropic: venv
	$(PIP) install -e ".[ai-anthropic]"
	$(PIP) install -r requirements-dev.txt

install-ai-openai: venv
	$(PIP) install -e ".[ai-openai]"
	$(PIP) install -r requirements-dev.txt

install-ai-all: venv
	$(PIP) install -e ".[ai-all]"
	$(PIP) install -r requirements-dev.txt

# ── Dev ──────────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/

test-v:
	$(PYTEST) tests/ -v

coverage:
	$(PYTEST) tests/ --tb=short \
	  --cov=shared --cov=dividend \
	  --cov-report=term-missing \
	  --cov-fail-under=80

lint:
	$(VENV)/bin/ruff check shared/ dividend/ tests/

fmt:
	$(VENV)/bin/ruff format shared/ dividend/ tests/

check: lint test

# ── Ops ──────────────────────────────────────────────────────────────────────

cache-clear:
	rm -f .cache/market_data.json
	@echo "Cache cleared."

clean:
	rm -rf $(VENV) .cache __pycache__ stock_screeners.egg-info \
	  $$(find . -name "__pycache__" -not -path "./.venv/*") \
	  $$(find . -name "*.pyc" -not -path "./.venv/*")
