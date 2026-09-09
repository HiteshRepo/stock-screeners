"""Configuration dataclasses and YAML loader for the momentum screener."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScoringConfig:
    # Core momentum parameters
    lookback_months: int = 12               # Return window in months
    skip_recent_months: int = 1             # Skip most-recent N months (avoids short-term reversal)
    top_n: int = 30                         # Portfolio size
    min_daily_traded_value_cr: float = 2.0  # Min avg daily traded value (₹ crore)
    corporate_action_threshold: float = 0.30  # Flag single-day moves > this fraction

    # Secondary filter toggles (each off by default — run baseline first)
    use_pct_positive_days: bool = False
    use_dist_from_52w_high: bool = False
    use_sharpe_ratio: bool = False

    # Secondary filter parameters
    pct_positive_days_window_months: int = 6
    pct_positive_days_weight: float = 0.20
    dist_from_52w_high_weight: float = 0.20
    sharpe_ratio_weight: float = 0.20


@dataclass
class MomentumConfig:
    db_path: Path
    universe_path: Path
    runs_dir: Path
    holdings_path: Path
    scoring: ScoringConfig
    whatsapp_api_key: str | None
    whatsapp_phone: str | None


_DEFAULTS: dict[str, Any] = {
    "db_path": ".cache/momentum.db",
    "universe_path": "momentum/data/nifty500.csv",
    "runs_dir": "momentum/data/runs",
    "holdings_path": "momentum/data/holdings.md",
    "whatsapp_api_key": None,
    "whatsapp_phone": None,
    "scoring": {
        "lookback_months": 12,
        "skip_recent_months": 1,
        "top_n": 30,
        "min_daily_traded_value_cr": 2.0,
        "corporate_action_threshold": 0.30,
        "use_pct_positive_days": False,
        "use_dist_from_52w_high": False,
        "use_sharpe_ratio": False,
        "pct_positive_days_window_months": 6,
        "pct_positive_days_weight": 0.20,
        "dist_from_52w_high_weight": 0.20,
        "sharpe_ratio_weight": 0.20,
    },
}


def load_config(path: Path | str = "momentum/config.yaml") -> MomentumConfig:
    """Load config from YAML, falling back to _DEFAULTS for any missing keys."""
    p = Path(path)
    raw: dict[str, Any] = {}
    if p.exists():
        with open(p) as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                raw = loaded

    def _get(key: str) -> Any:
        return raw.get(key, _DEFAULTS[key])

    raw_scoring = {**_DEFAULTS["scoring"], **raw.get("scoring", {})}
    valid_fields = set(ScoringConfig.__dataclass_fields__)
    scoring = ScoringConfig(**{k: v for k, v in raw_scoring.items() if k in valid_fields})

    return MomentumConfig(
        db_path=Path(_get("db_path")),
        universe_path=Path(_get("universe_path")),
        runs_dir=Path(_get("runs_dir")),
        holdings_path=Path(_get("holdings_path")),
        scoring=scoring,
        whatsapp_api_key=_get("whatsapp_api_key"),
        whatsapp_phone=_get("whatsapp_phone"),
    )
