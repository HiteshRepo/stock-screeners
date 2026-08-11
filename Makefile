VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
DIVVY  := $(VENV)/bin/divvy
DIVVY_TEST := $(DIVVY) --config-file dividend/config.test.yaml

# Overridable variables for buy/sell/recommend/ai
TICKER ?=
SHARES ?=
PRICE  ?=
AMOUNT ?= 10000
TOP    ?= 3

.DEFAULT_GOAL := help

.PHONY: help venv install install-ai-anthropic install-ai-openai install-ai-all \
        test test-v coverage lint fmt check clean cache-clear \
        status status-refresh \
        review review-refresh \
        recommend recommend-refresh \
        buy sell \
        watchlist portfolio transactions \
        ai-narrative ai-watchlist \
        test-status test-status-refresh \
        test-review test-review-refresh \
        test-recommend test-recommend-refresh \
        test-buy test-sell \
        test-watchlist test-portfolio test-transactions \
        test-cache-clear test-quote test-reset

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
	@echo "Divvy — portfolio"
	@echo "  status                Live portfolio dashboard (cached)"
	@echo "  status-refresh        Live portfolio dashboard (force-refresh)"
	@echo "  review                Flag holdings with yield/price issues (cached)"
	@echo "  review-refresh        Flag holdings (force-refresh)"
	@echo "  recommend             Top-N candidates  AMOUNT=50000 TOP=5"
	@echo "  recommend-refresh     Same, force-refresh market data"
	@echo "  buy                   Record a buy  TICKER=HDFCBANK SHARES=10 PRICE=1650"
	@echo "  sell                  Record a sell TICKER=HDFCBANK SHARES=5 PRICE=1800"
	@echo ""
	@echo "Divvy — data files"
	@echo "  watchlist             Open watchlist.md in \$$EDITOR to add/remove candidates"
	@echo "  portfolio             Open portfolio.md in \$$EDITOR"
	@echo "  transactions          Open transactions.md in \$$EDITOR (read-only audit trail)"
	@echo ""
	@echo "Divvy — AI skills"
	@echo "  ai-narrative          Portfolio health briefing (LLM)"
	@echo "  ai-watchlist          Research brief for a ticker  TICKER=POWERGRID"
	@echo "  test-ai-watchlist     Research brief for a ticker (test data)  TICKER=POWERGRID"
	@echo "  eval-watchlist-brief  Run promptfoo eval across all models (needs npx)"
	@echo "  eval-portfolio        Run promptfoo eval for portfolio-narrative across all models"
	@echo ""
	@echo "Divvy — test data  (uses dividend/config.test.yaml)"
	@echo "  test-status           status with test data"
	@echo "  test-status-refresh   status with test data (force-refresh)"
	@echo "  test-review           review with test data"
	@echo "  test-review-refresh   review with test data (force-refresh)"
	@echo "  test-recommend        recommend with test data  AMOUNT=10000 TOP=3"
	@echo "  test-recommend-refresh  same, force-refresh"
	@echo "  test-buy              Record a buy  TICKER=ITC SHARES=10 PRICE=400"
	@echo "  test-sell             Record a sell TICKER=ITC SHARES=5  PRICE=450"
	@echo "  test-watchlist        Open test watchlist.md in \$$EDITOR"
	@echo "  test-portfolio        Open test portfolio.md in \$$EDITOR"
	@echo "  test-transactions     Open test transactions.md in \$$EDITOR"
	@echo "  test-cache-clear      Delete .cache/market_data_test.json"
	@echo "  test-quote            Dump raw price+dividend data for a ticker  TICKER=HDFCBANK"
	@echo "  test-reset            Reset test data files to empty (headers only) + clear test cache"
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

# ── Divvy — portfolio ─────────────────────────────────────────────────────────

status:
	$(DIVVY) status

status-refresh:
	$(DIVVY) status --refresh

review:
	$(DIVVY) review

review-refresh:
	$(DIVVY) review --refresh

recommend:
	$(DIVVY) recommend --amount $(AMOUNT) --top $(TOP)

recommend-refresh:
	$(DIVVY) recommend --amount $(AMOUNT) --top $(TOP) --refresh

buy:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make buy TICKER=HDFCBANK SHARES=10 PRICE=1650" && exit 1)
	@test -n "$(SHARES)" || (echo "Error: SHARES is required.  make buy TICKER=$(TICKER) SHARES=10 PRICE=1650" && exit 1)
	@test -n "$(PRICE)"  || (echo "Error: PRICE is required.   make buy TICKER=$(TICKER) SHARES=$(SHARES) PRICE=1650" && exit 1)
	$(DIVVY) buy --ticker $(TICKER) --shares $(SHARES) --price $(PRICE)

sell:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make sell TICKER=HDFCBANK SHARES=5 PRICE=1800" && exit 1)
	@test -n "$(SHARES)" || (echo "Error: SHARES is required.  make sell TICKER=$(TICKER) SHARES=5 PRICE=1800" && exit 1)
	@test -n "$(PRICE)"  || (echo "Error: PRICE is required.   make sell TICKER=$(TICKER) SHARES=$(SHARES) PRICE=1800" && exit 1)
	$(DIVVY) sell --ticker $(TICKER) --shares $(SHARES) --price $(PRICE)

# ── Divvy — data files ────────────────────────────────────────────────────────

watchlist:
	$${EDITOR:-vi} dividend/data/watchlist.md

portfolio:
	$${EDITOR:-vi} dividend/data/portfolio.md

transactions:
	$${EDITOR:-vi} dividend/data/transactions.md

# ── Divvy — AI skills ─────────────────────────────────────────────────────────

ai-narrative:
	$(DIVVY) ai portfolio-narrative

ai-watchlist:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make ai-watchlist TICKER=POWERGRID" && exit 1)
	$(DIVVY) ai watchlist-brief --ticker $(TICKER)

test-ai-watchlist:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make test-ai-watchlist TICKER=POWERGRID" && exit 1)
	$(DIVVY_TEST) ai watchlist-brief --ticker $(TICKER)

eval-watchlist-brief:
	cd dividend/skills/watchlist_brief/eval && npx promptfoo@latest eval --config promptfooconfig.yaml --no-cache

eval-portfolio:
	cd dividend/skills/portfolio_narrative/eval && npx promptfoo@latest eval --config promptfooconfig.yaml --no-cache

# ── Divvy — test data ────────────────────────────────────────────────────────

test-status:
	$(DIVVY_TEST) status

test-status-refresh:
	$(DIVVY_TEST) status --refresh

test-review:
	$(DIVVY_TEST) review

test-review-refresh:
	$(DIVVY_TEST) review --refresh

test-recommend:
	$(DIVVY_TEST) recommend --amount $(AMOUNT) --top $(TOP)

test-recommend-refresh:
	$(DIVVY_TEST) recommend --amount $(AMOUNT) --top $(TOP) --refresh

test-buy:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make test-buy TICKER=ITC SHARES=10 PRICE=400" && exit 1)
	@test -n "$(SHARES)" || (echo "Error: SHARES is required.  make test-buy TICKER=$(TICKER) SHARES=10 PRICE=400" && exit 1)
	@test -n "$(PRICE)"  || (echo "Error: PRICE is required.   make test-buy TICKER=$(TICKER) SHARES=$(SHARES) PRICE=400" && exit 1)
	$(DIVVY_TEST) buy --ticker $(TICKER) --shares $(SHARES) --price $(PRICE)

test-sell:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make test-sell TICKER=ITC SHARES=5 PRICE=450" && exit 1)
	@test -n "$(SHARES)" || (echo "Error: SHARES is required.  make test-sell TICKER=$(TICKER) SHARES=5 PRICE=450" && exit 1)
	@test -n "$(PRICE)"  || (echo "Error: PRICE is required.   make test-sell TICKER=$(TICKER) SHARES=$(SHARES) PRICE=450" && exit 1)
	$(DIVVY_TEST) sell --ticker $(TICKER) --shares $(SHARES) --price $(PRICE)

test-watchlist:
	$${EDITOR:-vi} dividend/data/test/watchlist.md

test-portfolio:
	$${EDITOR:-vi} dividend/data/test/portfolio.md

test-transactions:
	$${EDITOR:-vi} dividend/data/test/transactions.md

test-cache-clear:
	rm -f .cache/market_data_test.json
	@echo "Test cache cleared."

test-reset:
	cp dividend/data/test/seeds/portfolio.md     dividend/data/test/portfolio.md
	cp dividend/data/test/seeds/watchlist.md     dividend/data/test/watchlist.md
	cp dividend/data/test/seeds/transactions.md  dividend/data/test/transactions.md
	rm -f .cache/market_data_test.json
	@echo "Test data reset to empty state."

test-quote:
	@test -n "$(TICKER)" || (echo "Error: TICKER is required.  make test-quote TICKER=HDFCBANK" && exit 1)
	$(PYTHON) -m shared.market_data $(TICKER)

# ── Ops ──────────────────────────────────────────────────────────────────────

cache-clear:
	rm -f .cache/market_data.json
	@echo "Cache cleared."

clean:
	rm -rf $(VENV) .cache __pycache__ stock_screeners.egg-info \
	  $$(find . -name "__pycache__" -not -path "./.venv/*") \
	  $$(find . -name "*.pyc" -not -path "./.venv/*")
