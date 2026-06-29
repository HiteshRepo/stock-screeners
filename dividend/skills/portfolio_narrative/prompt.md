Today: {{ today }}

## Portfolio snapshot

Holdings (JSON):
```
{{ holdings }}
```

Total invested: {{ total_invested }}
Current market value: {{ total_value }}

Goals:
```
{{ goals }}
```

---

Write a 3–4 paragraph portfolio health briefing covering:

**1. Overall performance**
Total invested vs current value. Which 1–2 holdings contributed most to gains or losses (cite ticker, ₹ P&L, and %). Note any fetch errors briefly.

**2. Dividend income**
Estimated annual dividend income (shares × current_price × current_yield_pct / 100, summed across all holdings with valid data). Name the top 1–2 income contributors. Express as ₹ per year.

**3. Concerns**
Flag any holding where: (a) unrealized_pnl is worse than −15% of total_invested for that position, OR (b) entry_yield_pct was recorded and current_yield_pct has dropped more than 20% relatively. If none, say so briefly.

**4. Goal progress**
For each goal, state current value vs target and the raw percentage progress. If the portfolio value is growing, give a rough qualitative sense of timeline — fast/slow/on track.

Start directly with paragraph 1. No headers needed.
