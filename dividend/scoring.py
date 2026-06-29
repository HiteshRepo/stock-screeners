"""
dividend.scoring — scoring heuristics for the recommend command.

Ranks watchlist candidates by a weighted combination of three factors:

  yield_score        — trailing dividend yield (higher = better)
  div_score          — sector diversification vs. current portfolio
  value_score        — proximity to 52-week high (lower price = better entry)

Default weights: yield 40%, diversification 35%, value 25%.
All scores are normalized to [0, 1] so weights are directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .md_io import Holding, WatchlistItem
    from shared.market_data import QuoteResult


@dataclass
class CandidateScore:
    item: "WatchlistItem"
    quote: "QuoteResult"
    max_shares: int             # max whole shares affordable within budget
    cost_for_max_shares: float  # max_shares × price
    yield_score: float          # normalized 0–1
    div_score: float            # normalized 0–1
    value_score: float          # normalized 0–1
    total_score: float          # weighted sum
    already_held_shares: float  # 0 if not currently in portfolio


def score_candidates(
    watchlist_items: list["WatchlistItem"],
    quotes: dict[str, "QuoteResult"],
    holdings: list["Holding"],
    budget: float,
    yield_weight: float = 0.40,
    div_weight: float = 0.35,
    value_weight: float = 0.25,
) -> list[CandidateScore]:
    """
    Score and rank watchlist candidates.

    Filters out items where the quote is invalid or price exceeds budget.
    Returns a list sorted by total_score descending.

    Args:
        watchlist_items: candidates from watchlist.md
        quotes:          fetch_quotes() result keyed by ns_ticker
        holdings:        current portfolio holdings (for sector allocation)
        budget:          investable amount in ₹
        yield_weight:    weight for yield score (default 0.40)
        div_weight:      weight for diversification score (default 0.35)
        value_weight:    weight for value/entry score (default 0.25)
    """
    # Current portfolio: sector → total invested
    sector_totals: dict[str, float] = {}
    portfolio_total = sum(h.total_invested for h in holdings)
    for h in holdings:
        sector_totals[h.sector] = sector_totals.get(h.sector, 0) + h.total_invested

    # Filter to valid, affordable candidates
    valid: list[tuple[WatchlistItem, QuoteResult]] = []
    for item in watchlist_items:
        q = quotes.get(item.ns_ticker)
        if not q or not q.is_valid:
            continue
        if q.price is None or q.price > budget:
            continue
        valid.append((item, q))

    if not valid:
        return []

    # Pre-compute normalization denominators
    max_yield = max((q.yield_pct or 0.0) for _, q in valid) or 1.0
    max_below = max((q.pct_below_52w_high or 0.0) for _, q in valid) or 1.0

    scores: list[CandidateScore] = []
    for item, q in valid:
        # --- Yield score ---
        yield_s = (q.yield_pct or 0.0) / max_yield

        # --- Diversification score ---
        # Low sector allocation in current portfolio → high score
        sector_pct = (
            sector_totals.get(item.sector, 0.0) / portfolio_total * 100
            if portfolio_total > 0
            else 0.0
        )
        div_s = 1.0 - min(sector_pct / 100.0, 1.0)

        # --- Value / entry score ---
        below = q.pct_below_52w_high or 0.0
        value_s = below / max_below

        total = yield_weight * yield_s + div_weight * div_s + value_weight * value_s

        max_sh = int(floor(budget / q.price))
        held = next(
            (h.shares for h in holdings if h.ticker.upper() == item.ticker.upper()),
            0.0,
        )

        scores.append(CandidateScore(
            item=item,
            quote=q,
            max_shares=max_sh,
            cost_for_max_shares=round(max_sh * q.price, 2),
            yield_score=round(yield_s, 4),
            div_score=round(div_s, 4),
            value_score=round(value_s, 4),
            total_score=round(total, 4),
            already_held_shares=held,
        ))

    return sorted(scores, key=lambda s: s.total_score, reverse=True)


def build_rationale(
    score: CandidateScore,
    sector_totals: dict[str, float],
    portfolio_total: float,
) -> str:
    """
    Return a 1–2 sentence explanation of why this candidate ranked where it did.
    Focuses on the factors that most contributed to the score.
    """
    parts: list[str] = []

    # Yield
    y = score.quote.yield_pct or 0.0
    if y >= 5.0:
        parts.append(f"very high yield ({y:.1f}%)")
    elif y >= 3.0:
        parts.append(f"solid yield ({y:.1f}%)")
    elif y >= 1.5:
        parts.append(f"decent yield ({y:.1f}%)")
    elif y > 0:
        parts.append(f"low yield ({y:.1f}%) — growth play")
    else:
        parts.append("no dividend data available")

    # Diversification
    sector = score.item.sector
    sector_pct = (
        sector_totals.get(sector, 0.0) / portfolio_total * 100
        if portfolio_total > 0
        else 0.0
    )
    if sector_pct == 0.0:
        parts.append(f"{sector} sector not yet in portfolio")
    elif sector_pct < 15.0:
        parts.append(f"{sector} is underweight ({sector_pct:.0f}% of cost basis)")
    elif sector_pct > 40.0:
        parts.append(f"⚠ {sector} already {sector_pct:.0f}% of portfolio — adds concentration")

    # Value entry
    below = score.quote.pct_below_52w_high
    if below is not None:
        if below >= 25.0:
            parts.append(f"deep discount entry ({below:.1f}% off 52w high)")
        elif below >= 12.0:
            parts.append(f"reasonable entry ({below:.1f}% off 52w high)")
        elif below < 3.0:
            parts.append(f"near 52w high ({below:.1f}% below) — limited margin of safety")

    return "; ".join(parts) + "." if parts else "balanced score across all factors."
