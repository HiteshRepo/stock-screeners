# stock-screeners

Personal stock portfolio tools for Indian markets (NSE/BSE).

| Tool | CLI command | Purpose |
|------|-------------|---------|
| **Divvy** | `divvy` | Buy-and-hold dividend portfolio tracker |

> **Privacy note:** `dividend/data/` contains your actual holdings and buy prices.
> Use a **private** GitHub repo (`gh repo create --private`) — you get the full git history
> benefit without exposing financial data publicly.

---

## Divvy — dividend portfolio manager

No broker API needed. Portfolio state lives in three plain markdown files you commit to
git. Every buy and sell is recorded; `review` flags problems; `recommend` suggests what
to buy next from your watchlist.

---

## Setup

```bash
# 1. Create your private repo
git init
gh repo create --private

# 2. Install (run once; creates the `divvy` CLI command)
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .

# 3. Verify
divvy --help
```

Always run `divvy` from the **repo root** so the relative paths in `dividend/config.yaml`
resolve correctly.

---

## Typical workflow

```
Initial setup
  └─ Add candidate stocks to watchlist.md (manually)

When you have spare cash
  1. divvy recommend --amount 25000   → see top-3 picks from your watchlist
  2. Buy via your broker app
  3. divvy buy --ticker ITC --shares 50 --price 400   → records the buy

Periodically
  └─ divvy review        → flags holdings with price/yield deterioration
  └─ divvy status        → full dashboard: value, income, goals
```

---

## Commands

### `divvy status`

Full portfolio dashboard. Fetches live prices and shows:
- Holdings table with current value and P&L per stock
- Total invested, current market value, estimated annual dividend income
- Sector allocation breakdown
- Progress toward goals defined in `config.yaml`

```bash
divvy status              # use cached prices (up to 24h old by default)
divvy status --refresh    # force-fetch fresh prices from Yahoo Finance
```

---

### `divvy buy`

Records a buy you made via your broker app. Updates `portfolio.md` (new row or
weighted-average top-up) and appends to `transactions.md`.

```bash
divvy buy --ticker HDFCBANK --shares 10 --price 1650

# Optional flags
--company "HDFC Bank"    # required for new holdings not in your watchlist
--sector Banking         # required for new holdings not in your watchlist
--investable-amount 25000  # logs how much cash you had available (audit trail)
--notes "post-results dip"
```

For tickers already in your watchlist, `--company` and `--sector` are auto-populated.
For tickers not in your watchlist, the tool tries a yfinance lookup for the company name;
`--sector` defaults to `Unknown` if not provided (you can edit `portfolio.md` directly).

You'll always see a preview and a `Proceed? [y/N]` prompt before anything is written.

---

### `divvy sell`

Records a sell. Partial sells reduce the share count (avg buy price is preserved).
Full sells remove the holding from `portfolio.md`.

```bash
divvy sell --ticker ITC --shares 25 --price 450

# Optional
--notes "trimming position"
```

Shows proceeds, cost basis, and realized P&L before asking for confirmation.

---

### `divvy review`

Fetches current prices for every holding and flags anything that needs attention.
**Read-only for investment data** — it only updates the `Last Reviewed` date.

```bash
divvy review              # uses cached prices
divvy review --refresh    # force-fetch before reviewing
```

Two flags are checked per holding:

| Flag | Condition | Default threshold |
|------|-----------|-------------------|
| Price drop | Current price is X% below your avg buy price | 15% |
| Yield drop | Current yield dropped X% *relative* to yield at time of buy | 20% |

Thresholds are configurable in `dividend/config.yaml`.

The yield drop check only fires if `Entry Yield %` was recorded at buy time
(automatically captured by `divvy buy` via yfinance). Holdings added manually to
`portfolio.md` without that column will show "no entry yield recorded" and skip the
yield check.

Output per holding:
```
✅  POWERGRID  Power Grid Corp  (Utilities)   → all clear
⚠   ITC        ITC Ltd          (FMCG)        → price 27% below avg buy
❌  BADTICK    Bad Company      (Unknown)      → fetch failed
```

---

### `divvy recommend`

Scores your watchlist and suggests what to buy given a cash amount.
**Advisory only — makes no changes to any file.**

```bash
divvy recommend --amount 25000
divvy recommend --amount 10000 --top 5    # show top 5 instead of default 3
divvy recommend --amount 25000 --refresh  # force-refresh prices first
```

Stocks are scored on three factors (weights shown):

| Factor | Weight | Logic |
|--------|--------|-------|
| Dividend yield | 40% | Higher trailing yield → higher score |
| Sector diversification | 35% | Sectors absent from your portfolio score highest |
| Entry point | 25% | Larger discount from 52-week high → higher score |

Each recommendation shows the score breakdown, how many shares you can buy, and a
one-line "Why" explanation.

After reviewing the output, use `divvy buy` to record whichever pick you act on.

---

## File schemas

All three files live in `dividend/data/` and are committed to git.
The tool reads and writes them as markdown tables. You can hand-edit any value between
runs — the parser is lenient about column widths and extra whitespace.
**Do not add extra markdown sections** to these files; they are fully managed by the tool.

### `portfolio.md` — current holdings

| Column | Notes |
|--------|-------|
| Ticker | Plain NSE ticker, e.g. `HDFCBANK`. Use `TICKER.BO` for BSE-only stocks. |
| Company | Full company name |
| Sector | e.g. `Banking`, `FMCG`, `IT`, `Mining`, `Utilities` |
| Shares | Total shares currently held |
| Avg Buy Price (₹) | Weighted average cost basis — recalculated automatically on top-ups |
| Total Invested (₹) | Shares × avg buy price |
| Date Added | YYYY-MM-DD — date of first purchase |
| Last Reviewed | YYYY-MM-DD — set automatically by `divvy review` |
| Notes | Free text |
| Entry Yield % | Trailing yield at time of first buy — captured automatically by `divvy buy` |

### `watchlist.md` — candidates not yet purchased

Maintain this file manually. Add a row for each stock you've pre-vetted.
`divvy recommend` reads this file.

| Column | Notes |
|--------|-------|
| Ticker | Same format as portfolio |
| Company | |
| Sector | |
| Yield % | Last known trailing yield (your research baseline) |
| Payout Ratio % | Last known payout ratio |
| Notes | Research notes, e.g. "high debt, monitor" |
| Date Added | YYYY-MM-DD |

### `transactions.md` — append-only audit log

Never delete rows from this file. Every `buy` and `sell` appends here.

| Column | Notes |
|--------|-------|
| Date | YYYY-MM-DD |
| Type | `BUY` or `SELL` |
| Ticker | |
| Company | |
| Shares | |
| Price (₹) | Per-share execution price |
| Amount (₹) | Total = shares × price |
| Investable Amount (₹) | Cash you had available at that time — optional audit field |
| Notes | |

---

## Configuration (`dividend/config.yaml`)

```yaml
# Paths to data files (relative to repo root)
files:
  portfolio:    dividend/data/portfolio.md
  watchlist:    dividend/data/watchlist.md
  transactions: dividend/data/transactions.md
  cache:        .cache/market_data.json     # gitignored

# How long fetched market data is reused before a live fetch (hours)
cache_expiry_hours: 24

# Thresholds for `divvy review`
thresholds:
  price_drop_pct: 15.0   # flag if price > 15% below avg buy price
  yield_drop_pct: 20.0   # flag if yield dropped > 20% relative to entry yield

# Portfolio goals — shown in `divvy status`
# Progress = current market value / target
goals:
  fuel-fund: 1500000      # ₹15,00,000
  # vacation-fund: 500000
```

---

---

## AI skills (`divvy ai`)

LLM-powered analysis on top of your portfolio data. Skills are provider-agnostic —
the same skill runs against Claude, GPT-4, or a local Ollama model by changing one
line in `config.yaml`.

### Setup

```bash
# Install the SDK for whichever provider you want to use
pip install -e ".[ai-anthropic]"    # Claude (recommended)
pip install -e ".[ai-openai]"       # GPT-4o / GPT-4o-mini
# Ollama: no extra package needed — install from https://ollama.com and run `ollama serve`
```

Set your API key as an environment variable:
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # for Anthropic
export OPENAI_API_KEY=sk-...          # for OpenAI
```

Configure in `dividend/config.yaml`:
```yaml
ai:
  provider: anthropic                 # anthropic | openai | ollama
  model: claude-haiku-4-5-20251001   # fast + cheap for portfolio tasks
```

### Available skills

```bash
divvy ai portfolio-narrative
```
Generates a plain-English portfolio health briefing covering: overall performance
(winners/losers with ₹ P&L), estimated annual dividend income, concerns (price drops,
yield deterioration), and goal progress.

```bash
divvy ai watchlist-brief --ticker POWERGRID
```
Research brief for a ticker covering: business snapshot, dividend quality rating,
3 key risks, portfolio fit (diversification + entry point), and a Buy/Watch/Avoid verdict.
Works for any NSE ticker, not just ones already on your watchlist.

### Common flags

```bash
--provider openai --model gpt-4o-mini   # override provider per-run
--provider ollama --model llama3.1      # run locally, no API cost
--refresh                               # force-fetch fresh prices before running
```

### Skill folder structure

Skills live in `dividend/skills/<skill-name>/` and are fully LLM-agnostic:

```
dividend/skills/
├── portfolio_narrative/
│   ├── skill.yaml     # metadata: inputs, max_tokens, compatible models
│   ├── prompt.md      # Jinja2 template with {{ variable }} placeholders
│   └── context.py     # gather(cfg, **kwargs) → dict fed into the template
└── watchlist_brief/
    ├── skill.yaml
    ├── prompt.md
    └── context.py
```

The LLM runner infrastructure (`shared/llm/`) is shared across all tools in this repo.
To add a new skill: create the directory, write `skill.yaml`, `prompt.md`, and
`context.py` — no changes to the CLI needed.

See `TODO.md` for planned skills: `review-analyst`, `sell-thesis`, `portfolio-query`.

---

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Adding a future tool (e.g. trade recommender)

1. Create `trade/` mirroring the `dividend/` structure
2. Put any reusable logic (data fetching, table parsing) in `shared/`
3. Add an entry point to `pyproject.toml`:
   ```toml
   [project.scripts]
   tradr = "trade.cli:main"
   ```
4. `pip install -e .` to pick up the new command
