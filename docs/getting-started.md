# Getting started with Divvy

A step-by-step walkthrough for first-time users. By the end you'll have
a working portfolio tracker, your first buy recorded, and a routine for
periodic reviews.

---

## Prerequisites

- Python 3.10 or higher (`python3 --version`)
- Git

---

## Step 1 — Create a private repo and install

Your portfolio files contain real holdings and buy prices. Keep them in a
**private** repository.

```bash
# Clone or init the repo
git clone <your-private-repo-url>
cd stock-screeners

# Install everything (creates .venv, installs divvy CLI)
make install

# Confirm it worked
.venv/bin/divvy --help
```

> After `make install`, activate the venv once per terminal session so you
> can call `divvy` directly instead of `.venv/bin/divvy`:
> ```bash
> source .venv/bin/activate   # macOS / Linux
> .venv\Scripts\activate      # Windows
> ```

---

## Step 2 — Add candidate stocks to your watchlist

The watchlist is the pool `divvy recommend` draws from. Start with 5–10
stocks you've already researched.

```bash
make watchlist   # opens dividend/data/watchlist.md in your $EDITOR
```

Add a row per stock. Example:

```markdown
| Ticker    | Company         | Sector    | Yield % | Payout Ratio % | Notes              | Date Added |
|-----------|-----------------|-----------|---------|----------------|--------------------|------------|
| POWERGRID | Power Grid Corp | Utilities | 4.50    | 65.00          | Stable PSU         | 2026-08-01 |
| HINDUNILVR| Hindustan Unilever | FMCG   | 1.80    | 95.00          | Quality compounder | 2026-08-01 |
| COALINDIA | Coal India Ltd  | Mining    | 7.80    | 60.00          | High yield PSU     | 2026-08-01 |
```

**Ticker format:** use plain NSE tickers (`POWERGRID`, not `POWERGRID.NS`).
The tool appends `.NS` internally. For BSE-only stocks use `TICKER.BO`.

---

## Step 3 — Get a buy recommendation

When you have spare cash, ask divvy which watchlist stock to buy:

```bash
make recommend AMOUNT=25000
```

Output shows the top-3 ranked candidates scored on yield (40%), sector
diversification vs. your current portfolio (35%), and discount from 52-week
high (25%). Example:

```
Recommendations for ₹25,000

  #1  Power Grid Corp (POWERGRID)
      Sector: Utilities  |  Price: ₹320.50  |  Can buy: 78 shares @ ₹24,999
      Yield: 4.52%  |  52w high: ₹366.40 (12.5% below)
      Score: 0.82  (yield 0.91 × 0.40 + div 0.85 × 0.35 + value 0.64 × 0.25)
      Why: Highest yield; Utilities under-represented (0% of portfolio); good entry point
```

> This command is **read-only** — it changes nothing. Use it as a starting
> point, then decide via your own broker app.

---

## Step 4 — Buy via your broker, then record it

After executing the trade in your broker app, tell divvy:

```bash
make buy TICKER=POWERGRID SHARES=78 PRICE=320.50
```

You'll see a confirmation preview:

```
About to record:

  NEW HOLDING: POWERGRID — Power Grid Corp (Utilities)
  78 shares @ ₹320.50 = ₹24,999.00

Proceed? [y/N]:
```

Press `y`. Divvy writes to `dividend/data/portfolio.md` and appends to
`dividend/data/transactions.md`. Commit the changes:

```bash
git add dividend/data/
git commit -m "buy: POWERGRID 78 shares @ 320.50"
```

### Topping up an existing holding

Same command — divvy detects the ticker already exists and calculates a
new weighted-average buy price:

```bash
make buy TICKER=POWERGRID SHARES=25 PRICE=310.00
# Shows: avg buy price ₹320.50 → ₹318.10
```

---

## Step 5 — Check your portfolio

```bash
make status
```

Shows current value, unrealized P&L, estimated annual dividend income,
sector breakdown, and progress toward goals defined in `dividend/config.yaml`.

Force-fetch fresh prices when the 24-hour cache feels stale:

```bash
make status-refresh
```

---

## Step 6 — Periodic review (weekly or before buying more)

```bash
make review
```

Checks every holding for:
- Price **>15%** below your average buy price
- Dividend yield **>20%** below what it was when you bought

```
✅  POWERGRID   Power Grid Corp  (Utilities)  → all clear
⚠   ITC         ITC Ltd          (FMCG)       → price 18% below avg buy
```

Fix nothing automatically — it's an alert to prompt your own research.
Run `make recommend` after reviewing to see if it's worth adding to
an underperforming position.

---

## Step 7 (optional) — AI-powered analysis

If you want a plain-English narrative instead of raw numbers, set up an
AI provider once:

```bash
# Install the SDK for your preferred provider
make install-ai-anthropic   # Claude (recommended)
make install-ai-openai      # GPT-4o / GPT-4o-mini

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
```

Then run:

```bash
make ai-narrative               # full portfolio health briefing in plain English
make ai-watchlist TICKER=INFY   # research brief + Buy/Watch/Avoid verdict
```

No API key? Run locally with Ollama (free, no internet needed):

```bash
# Install Ollama from https://ollama.com, then:
ollama pull llama3.1
ollama serve
```

Configure in `dividend/config.yaml`:
```yaml
ai:
  provider: ollama
  model: llama3.1
```

---

## Ongoing routine

```
Weekly (5 minutes)
  make review              ← any red flags?
  make status              ← current value and income

When you have spare cash
  make recommend AMOUNT=<cash>
  → buy via broker
  make buy TICKER=X SHARES=N PRICE=P
  git commit dividend/data/

After major market moves
  make status-refresh      ← force-fetch fresh prices
```

---

## Quick reference

| Goal | Command |
|------|---------|
| Edit watchlist | `make watchlist` |
| See portfolio | `make status` |
| Periodic health check | `make review` |
| Get buy suggestion | `make recommend AMOUNT=25000` |
| Record a buy | `make buy TICKER=X SHARES=N PRICE=P` |
| Record a sell | `make sell TICKER=X SHARES=N PRICE=P` |
| AI portfolio brief | `make ai-narrative` |
| AI stock brief | `make ai-watchlist TICKER=X` |
| Clear price cache | `make cache-clear` |
| All make targets | `make help` |

Full command reference, file schemas, and configuration options are in the
[README](../README.md).
