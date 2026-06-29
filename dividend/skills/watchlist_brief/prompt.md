Today: {{ today }}

## Stock under review

**{{ company }} ({{ ticker }})** — Sector: {{ sector }}
My notes: {{ watchlist_notes if watchlist_notes else "None" }}

Current market data:
```
{{ market_data }}
```

My existing portfolio sector allocation (% of cost basis):
```
{{ portfolio_sectors }}
```
Total already invested: {{ portfolio_total_invested }}

---

Write a structured research brief with these five sections:

### Business snapshot
2–3 sentences: what the company does, its competitive moat, and why it historically pays dividends (stable cash flows, PSU mandate, etc.).

### Dividend quality
Comment on: current yield vs sector norms, payout ratio sustainability (flag if >80% for cyclicals or >95% generally), whether dividends have grown or been cut in recent years (draw on training knowledge), and FCF coverage. Give a one-word quality rating: **Excellent / Good / Fair / Weak**.

### Key risks
3 specific bullet points — company or sector specific, not generic market risk.

### Portfolio fit
One paragraph: does this improve sector diversification given the allocation data above? Is the current price (vs 52w_high, 52w_low from market_data) an attractive or stretched entry? Would adding this push any sector above 30% of total invested?

### Verdict
**Buy / Watch / Avoid** — one sentence with the decisive reason.
