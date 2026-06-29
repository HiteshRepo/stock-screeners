"""Tests for dividend.config — YAML loading and default merging."""
import pytest
from pathlib import Path

from dividend.config import load_config


class TestLoadConfig:
    def test_defaults_when_file_missing(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.cache_expiry_hours == 24
        assert cfg.yield_drop_pct == pytest.approx(20.0)
        assert cfg.price_drop_pct == pytest.approx(15.0)
        assert cfg.goals == {}

    def test_default_file_paths(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.portfolio_path == Path("dividend/data/portfolio.md")
        assert cfg.watchlist_path == Path("dividend/data/watchlist.md")
        assert cfg.transactions_path == Path("dividend/data/transactions.md")
        assert cfg.cache_path == Path(".cache/market_data.json")

    def test_partial_override_thresholds(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "thresholds:\n  yield_drop_pct: 10.0\n",
            encoding="utf-8",
        )
        cfg = load_config(f)
        assert cfg.yield_drop_pct == pytest.approx(10.0)
        assert cfg.price_drop_pct == pytest.approx(15.0)  # default preserved

    def test_cache_expiry_override(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("cache_expiry_hours: 6\n", encoding="utf-8")
        cfg = load_config(f)
        assert cfg.cache_expiry_hours == 6

    def test_goals_parsed(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "goals:\n  fuel-fund: 1500000\n  vacation-fund: 500000\n",
            encoding="utf-8",
        )
        cfg = load_config(f)
        assert cfg.goals == {"fuel-fund": 1500000, "vacation-fund": 500000}

    def test_custom_file_paths(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "files:\n  portfolio: custom/portfolio.md\n",
            encoding="utf-8",
        )
        cfg = load_config(f)
        assert cfg.portfolio_path == Path("custom/portfolio.md")
        # Others fall back to defaults
        assert cfg.watchlist_path == Path("dividend/data/watchlist.md")

    def test_empty_yaml_file(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("", encoding="utf-8")
        cfg = load_config(f)
        assert cfg.cache_expiry_hours == 24  # defaults intact

    def test_returns_path_objects(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(cfg.portfolio_path, Path)
        assert isinstance(cfg.cache_path, Path)
