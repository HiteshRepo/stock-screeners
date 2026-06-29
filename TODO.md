# TODO — stock-screeners

## AI Skills (pending implementation)

Skill infrastructure is in `shared/llm/`. New skills follow the same pattern as
the two built skills: a directory under `dividend/skills/<name>/` with
`skill.yaml`, `prompt.md`, and `context.py`.

---

### `review_analyst`

**CLI:** `divvy ai review-analyst`

**What it does:**
When `divvy review` flags one or more holdings, this skill passes the flagged
holdings (with their flag reasons, current price, yield data, and sector) to an
LLM that provides:
- A qualitative "why it happened" — distinguishes sector-wide headwind from
  company-specific deterioration
- A hold / trim / exit recommendation with a 2–3 sentence rationale
- Suggested follow-up action (e.g. "check next earnings date", "review debt levels")

**Context needs:**
- Flagged holdings from the last `review` run (could persist to `.cache/last_review.json`)
  or re-run review logic internally
- Market data for flagged tickers (price, yield, 52w high)
- Holding period (from `date_added`)

**Prompt design note:**
Instruct the model to separate "macro/sector factor" from "company-specific factor"
as two explicit labels in its output to make the response actionable.

---

### `sell_thesis`

**CLI:** `divvy ai sell-thesis --ticker <TICKER>`

**What it does:**
Structures a sell decision for a specific holding:
- Tax angle: LTCG (held >1 year, 10% on gains >₹1L) vs STCG (held <1 year, 15%)
  calculated from `date_added` in portfolio.md
- Realized P&L at current price
- Portfolio impact: which sector allocation changes, what % cash freed up
- Redeployment suggestions: top 1–2 watchlist alternatives in under-represented sectors
- Final recommendation: sell now / wait for LTCG threshold / hold

**Context needs:**
- Specific holding (ticker, avg buy price, shares, date_added, total_invested)
- Current market price
- Holding period in days (compute from date_added)
- Portfolio sector allocation
- Top 2 watchlist candidates (run scoring internally)

**Prompt design note:**
The Indian tax rules (LTCG/STCG thresholds, ₹1L exemption) should be baked into
the system_prompt so the model applies them correctly without the user needing to
explain them.

---

### `portfolio_query`

**CLI:** `divvy ai query "<question>"`

**What it does:**
Natural language Q&A over portfolio data. Example questions:
- "Which holding has the most concentration risk?"
- "If COALINDIA cuts its dividend by 30%, what's my annual income impact?"
- "How much would I need to invest in FMCG to bring it to 25% of the portfolio?"
- "What's my total dividend income from PSU stocks only?"

**Context needs:**
- Full portfolio JSON (same as portfolio_narrative context)
- The user's question (passed as a CLI argument, e.g. `divvy ai query "..."`)

**Implementation note:**
The question becomes a `{{ question }}` variable in the prompt template.
The system prompt must strongly constrain the model to only use numbers from
the provided JSON — no estimation or fabrication. Include an explicit instruction:
"If the data to answer this question is not in the portfolio JSON, say so clearly."

**CLI change needed:**
`ai_cmd` in `dividend/commands/ai.py` needs an optional `--question` flag
(or positional argument after SKILL) passed through to `context.gather()`.

---

## Other enhancements

- [ ] `divvy ai --list` — print available skills with one-line descriptions
- [ ] Persist last `review` output to `.cache/last_review.json` so `review_analyst`
      can consume it without re-fetching prices
- [ ] Add `--dry-run` to `ai_cmd` that prints the rendered prompt without calling
      the LLM — useful for debugging / prompt iteration
- [ ] `divvy ai watchlist-brief` for a ticker not in watchlist.md
      (currently works — `context.py` handles missing watchlist entry gracefully)
- [ ] Streaming output for Anthropic/OpenAI providers (better UX for long responses)
- [ ] Token cost estimate printed after each AI call (based on provider pricing)
