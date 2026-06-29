"""
Tests for shared.llm infrastructure and dividend AI skills.

No real LLM calls are made — providers and fetch_quotes are fully mocked.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.llm.runner import LLMResponse, LLMRunner, create_runner
from shared.llm.skill import SkillDef, load_skill, render_prompt


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------

class TestLLMResponse:
    def test_fields(self):
        r = LLMResponse(content="hello", model="test-model",
                        input_tokens=10, output_tokens=5)
        assert r.content == "hello"
        assert r.model == "test-model"
        assert r.input_tokens == 10
        assert r.output_tokens == 5

    def test_optional_token_fields_default_none(self):
        r = LLMResponse(content="x", model="m")
        assert r.input_tokens is None
        assert r.output_tokens is None


# ---------------------------------------------------------------------------
# create_runner factory
# ---------------------------------------------------------------------------

class TestCreateRunner:
    def test_anthropic_returns_anthropic_runner(self):
        import sys, importlib
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            import shared.llm.providers.anthropic as mod
            importlib.reload(mod)
            runner = create_runner("anthropic", "claude-haiku-4-5-20251001")
            assert isinstance(runner, mod.AnthropicRunner)

    def test_openai_returns_openai_runner(self):
        import sys, importlib
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            import shared.llm.providers.openai as mod
            importlib.reload(mod)
            runner = create_runner("openai", "gpt-4o-mini")
            assert isinstance(runner, mod.OpenAIRunner)

    def test_ollama_returns_ollama_runner(self):
        from shared.llm.providers.ollama import OllamaRunner
        runner = create_runner("ollama", "llama3.1")
        assert isinstance(runner, OllamaRunner)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_runner("fakeai", "some-model")

    def test_case_insensitive_provider(self):
        from shared.llm.providers.ollama import OllamaRunner
        runner = create_runner("OLLAMA", "llama3.1")
        assert isinstance(runner, OllamaRunner)


# ---------------------------------------------------------------------------
# load_skill / render_prompt
# ---------------------------------------------------------------------------

class TestSkillLoader:
    def _write_skill(self, tmp_path: Path,
                     yaml_content: str, prompt_content: str) -> Path:
        skill_dir = tmp_path / "test_skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
        (skill_dir / "prompt.md").write_text(prompt_content, encoding="utf-8")
        return skill_dir

    def test_load_skill_reads_name_and_description(self, tmp_path):
        skill_dir = self._write_skill(
            tmp_path,
            "name: my_skill\ndescription: Does stuff\noutput:\n  max_tokens: 300\n",
            "Hello {{ name }}",
        )
        s = load_skill(skill_dir)
        assert s.name == "my_skill"
        assert s.description == "Does stuff"
        assert s.max_tokens == 300

    def test_load_skill_reads_system_prompt(self, tmp_path):
        skill_dir = self._write_skill(
            tmp_path,
            "name: x\nsystem_prompt: Be helpful.\noutput:\n  max_tokens: 100\n",
            "prompt",
        )
        s = load_skill(skill_dir)
        assert s.system_prompt == "Be helpful."

    def test_load_skill_defaults_max_tokens(self, tmp_path):
        skill_dir = self._write_skill(tmp_path, "name: x\n", "prompt")
        s = load_skill(skill_dir)
        assert s.max_tokens == 600  # default from skill.py

    def test_load_skill_missing_yaml_raises(self, tmp_path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="skill.yaml"):
            load_skill(skill_dir)

    def test_load_skill_missing_prompt_raises(self, tmp_path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: x\n", encoding="utf-8")
        with pytest.raises(FileNotFoundError, match="prompt.md"):
            load_skill(skill_dir)

    def test_render_prompt_substitutes_variables(self, tmp_path):
        skill_dir = self._write_skill(tmp_path, "name: x\n", "Hello {{ name }}, today is {{ today }}.")
        s = load_skill(skill_dir)
        result = render_prompt(s, {"name": "Hitesh", "today": "28 Jun 2026"})
        assert result == "Hello Hitesh, today is 28 Jun 2026."

    def test_render_prompt_raises_on_undefined_variable(self, tmp_path):
        skill_dir = self._write_skill(tmp_path, "name: x\n", "Hello {{ missing_var }}")
        s = load_skill(skill_dir)
        with pytest.raises(ValueError, match="undefined variable"):
            render_prompt(s, {})

    def test_render_prompt_jinja_conditionals(self, tmp_path):
        skill_dir = self._write_skill(
            tmp_path, "name: x\n",
            "{% if notes %}Notes: {{ notes }}{% else %}No notes.{% endif %}"
        )
        s = load_skill(skill_dir)
        assert render_prompt(s, {"notes": ""}) == "No notes."
        assert render_prompt(s, {"notes": "Good stock"}) == "Notes: Good stock"


# ---------------------------------------------------------------------------
# Anthropic provider (mocked)
# ---------------------------------------------------------------------------

class TestAnthropicRunner:
    def test_complete_calls_messages_create(self):
        import sys, importlib
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Portfolio looks healthy.")]
        mock_msg.usage.input_tokens = 120
        mock_msg.usage.output_tokens = 80

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_msg

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            import shared.llm.providers.anthropic as mod
            importlib.reload(mod)
            runner = mod.AnthropicRunner("claude-haiku-4-5-20251001")
            resp = runner.complete("Summarise this.", system="Be brief.")

        assert resp.content == "Portfolio looks healthy."
        assert resp.input_tokens == 120
        assert resp.output_tokens == 80

    def test_missing_package_raises_import_error(self):
        import sys, importlib
        with patch.dict(sys.modules, {"anthropic": None}):  # type: ignore[dict-item]
            import shared.llm.providers.anthropic as mod
            importlib.reload(mod)
            with pytest.raises(ImportError, match="pip install anthropic"):
                mod.AnthropicRunner("claude-haiku-4-5-20251001")


# ---------------------------------------------------------------------------
# Ollama provider (mocked)
# ---------------------------------------------------------------------------

class TestOllamaRunner:
    def test_complete_calls_generate_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": "Here is the analysis.",
            "prompt_eval_count": 50,
            "eval_count": 30,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            from shared.llm.providers.ollama import OllamaRunner
            runner = OllamaRunner("llama3.1")
            resp = runner.complete("Tell me about my portfolio.")

        assert resp.content == "Here is the analysis."
        assert resp.input_tokens == 50
        assert resp.output_tokens == 30

    def test_connection_error_gives_helpful_message(self):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.ConnectionError()):
            from shared.llm.providers.ollama import OllamaRunner
            runner = OllamaRunner("llama3.1")
            with pytest.raises(ConnectionError, match="ollama serve"):
                runner.complete("Hello")


# ---------------------------------------------------------------------------
# dividend/skills context gatherers
# ---------------------------------------------------------------------------

class TestPortfolioNarrativeContext:
    def test_gather_returns_required_keys(self, tmp_path):
        from dividend.md_io import Holding, write_portfolio
        from dividend.config import Config, AIConfig
        from shared.market_data import QuoteResult

        portfolio_path = tmp_path / "portfolio.md"
        write_portfolio(portfolio_path, [
            Holding("ITC", "ITC Ltd", "FMCG", 50, 400, 20000, "2025-01-01", "", "", 3.2)
        ])

        cfg = Config(
            portfolio_path=portfolio_path,
            watchlist_path=tmp_path / "watchlist.md",
            transactions_path=tmp_path / "transactions.md",
            cache_path=tmp_path / ".cache" / "data.json",
            cache_expiry_hours=24,
            yield_drop_pct=20.0,
            price_drop_pct=15.0,
            goals={"fuel-fund": 1500000},
        )

        mock_quote = QuoteResult("ITC.NS", 420.0, 3.5, 500.0, 350.0, "ITC Ltd", 80.0,
                                  None, datetime.now().isoformat())

        with patch("dividend.skills.portfolio_narrative.context.fetch_quotes",
                   return_value={"ITC.NS": mock_quote}):
            from dividend.skills.portfolio_narrative.context import gather
            ctx = gather(cfg)

        assert "holdings" in ctx
        assert "total_invested" in ctx
        assert "total_value" in ctx
        assert "goals" in ctx
        assert "today" in ctx
        # Verify it's valid JSON
        holdings = json.loads(ctx["holdings"])
        assert holdings[0]["ticker"] == "ITC"

    def test_gather_raises_on_empty_portfolio(self, tmp_path):
        from dividend.config import Config, AIConfig
        from dividend.md_io import ensure_data_files

        portfolio_path = tmp_path / "portfolio.md"
        watchlist_path = tmp_path / "watchlist.md"
        transactions_path = tmp_path / "transactions.md"
        ensure_data_files(portfolio_path, watchlist_path, transactions_path)

        cfg = Config(
            portfolio_path=portfolio_path,
            watchlist_path=watchlist_path,
            transactions_path=transactions_path,
            cache_path=tmp_path / ".cache" / "data.json",
            cache_expiry_hours=24,
            yield_drop_pct=20.0,
            price_drop_pct=15.0,
            goals={},
        )
        from dividend.skills.portfolio_narrative.context import gather
        with pytest.raises(ValueError, match="empty"):
            gather(cfg)


class TestWatchlistBriefContext:
    def test_gather_requires_ticker(self, tmp_path):
        from dividend.config import Config
        cfg = Config(
            portfolio_path=tmp_path / "p.md",
            watchlist_path=tmp_path / "w.md",
            transactions_path=tmp_path / "t.md",
            cache_path=tmp_path / ".cache" / "data.json",
            cache_expiry_hours=24,
            yield_drop_pct=20.0,
            price_drop_pct=15.0,
            goals={},
        )
        from dividend.skills.watchlist_brief.context import gather
        with pytest.raises(ValueError, match="--ticker"):
            gather(cfg, ticker="")

    def test_gather_returns_required_keys(self, tmp_path):
        from dividend.config import Config
        from dividend.md_io import WatchlistItem, write_watchlist
        from shared.market_data import QuoteResult

        watchlist_path = tmp_path / "watchlist.md"
        write_watchlist(watchlist_path, [
            WatchlistItem("POWERGRID", "Power Grid Corp", "Utilities",
                          4.5, 65.0, "Stable PSU", "2025-01-01")
        ])

        cfg = Config(
            portfolio_path=tmp_path / "portfolio.md",
            watchlist_path=watchlist_path,
            transactions_path=tmp_path / "transactions.md",
            cache_path=tmp_path / ".cache" / "data.json",
            cache_expiry_hours=24,
            yield_drop_pct=20.0,
            price_drop_pct=15.0,
            goals={},
        )

        mock_quote = QuoteResult("POWERGRID.NS", 284.5, 3.09, 324.95, 220.0,
                                  "Power Grid Corp", 65.0, None, datetime.now().isoformat())

        with patch("dividend.skills.watchlist_brief.context.fetch_quotes",
                   return_value={"POWERGRID.NS": mock_quote}):
            from dividend.skills.watchlist_brief.context import gather
            ctx = gather(cfg, ticker="POWERGRID")

        required = {"ticker", "company", "sector", "watchlist_notes",
                    "market_data", "portfolio_sectors", "portfolio_total_invested", "today"}
        assert required.issubset(ctx.keys())
        assert ctx["ticker"] == "POWERGRID"
        assert ctx["company"] == "Power Grid Corp"
