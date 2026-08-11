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
Comment on: current yield vs sector norms, payout ratio sustainability (flag if >80% for cyclicals or >95% generally; a payout below 60% is healthy), whether dividends have grown or been cut in recent years (draw on training knowledge), and FCF coverage. End with exactly this line: Quality: **Excellent** or Quality: **Good** or Quality: **Fair** or Quality: **Weak**.

### Key risks
3 specific bullet points — company or sector specific, not generic market risk.

### Portfolio fit
One paragraph: does this improve sector diversification given the allocation data above? Is the current price (vs 52w_high, 52w_low from market_data) an attractive or stretched entry? Would adding this push any sector above 30% of total invested?

### Verdict
**Buy / Watch / Avoid** — one sentence with the decisive reason.
Your verdict must follow directly from the four sections above. Use this as a guide:
- **Avoid**: payout > 85%, OR the sector would exceed 35% of the portfolio after adding this stock.
- **Buy**: yield ≥ 4% AND payout ≤ 70% AND price is ≥ 15% below 52w_high AND sector stays under 30%.
- **Watch**: everything else — fundamentals are acceptable but entry is not yet compelling.
