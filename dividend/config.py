"""
dividend.config — typed configuration loaded from config.yaml.

Provides safe defaults so the tool works out-of-the-box without any
config file present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import yaml

_DEFAULTS: dict = {
    "files": {
        "portfolio": "dividend/data/portfolio.md",
        "watchlist": "dividend/data/watchlist.md",
        "transactions": "dividend/data/transactions.md",
        "cache": ".cache/market_data.json",
    },
    "cache_expiry_hours": 24,
    "thresholds": {
        # Flag in `review` if trailing yield fell by more than this %
        # *relative* to the yield at time of purchase.
        # e.g. 20.0 means: if you bought at 5% yield and it's now below 4%, flag it.
        "yield_drop_pct": 20.0,
        # Flag in `review` if current price is more than this % below avg buy price.
        "price_drop_pct": 15.0,
    },
    "goals": {},
    "ai": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "ollama_base_url": "http://localhost:11434",
    },
}


@dataclass
class AIConfig:
    provider: str = "anthropic"           # anthropic | openai | ollama
    model: str = "claude-haiku-4-5-20251001"
    ollama_base_url: str = "http://localhost:11434"


@dataclass
class Config:
    portfolio_path: Path
    watchlist_path: Path
    transactions_path: Path
    cache_path: Path
    cache_expiry_hours: int
    yield_drop_pct: float
    price_drop_pct: float
    goals: Dict[str, int]  # {goal_name: target_rupees}
    ai: AIConfig = field(default_factory=AIConfig)


def load_config(path: Path | str = "dividend/config.yaml") -> Config:
    """Load config from *path*, falling back to built-in defaults for missing keys."""
    raw: dict = {}
    resolved = Path(path)
    if resolved.exists():
        with open(resolved, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    files = {**_DEFAULTS["files"], **raw.get("files", {})}
    thresholds = {**_DEFAULTS["thresholds"], **raw.get("thresholds", {})}
    goals = {str(k): int(v) for k, v in raw.get("goals", {}).items()}

    ai_raw = {**_DEFAULTS["ai"], **raw.get("ai", {})}
    ai = AIConfig(
        provider=ai_raw["provider"],
        model=ai_raw["model"],
        ollama_base_url=ai_raw["ollama_base_url"],
    )

    return Config(
        portfolio_path=Path(files["portfolio"]),
        watchlist_path=Path(files["watchlist"]),
        transactions_path=Path(files["transactions"]),
        cache_path=Path(files["cache"]),
        cache_expiry_hours=int(raw.get("cache_expiry_hours", _DEFAULTS["cache_expiry_hours"])),
        yield_drop_pct=float(thresholds["yield_drop_pct"]),
        price_drop_pct=float(thresholds["price_drop_pct"]),
        goals=goals,
        ai=ai,
    )
