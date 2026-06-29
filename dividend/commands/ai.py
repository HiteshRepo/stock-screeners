"""
dividend ai — run an LLM-powered skill against your portfolio data.

Skills live in dividend/skills/<skill_name>/
Each skill is a self-contained directory with:
  skill.yaml   — metadata, input list, output config, compatible models
  prompt.md    — Jinja2 prompt template
  context.py   — gather(cfg, **kwargs) → dict of template variables

The LLM provider is configured in dividend/config.yaml under the `ai:` key.
Override per-run with --provider / --model.
"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import click

from ..config import Config
from shared.llm.runner import create_runner
from shared.llm.skill import load_skill, render_prompt

# Root directory of all dividend skills (relative to this file)
_SKILLS_ROOT = Path(__file__).parent.parent / "skills"


def _available_skills() -> list[str]:
    if not _SKILLS_ROOT.exists():
        return []
    return sorted(
        d.name.replace("_", "-")
        for d in _SKILLS_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "skill.yaml").exists()
    )


@click.command("ai")
@click.argument("skill_name", metavar="SKILL")
@click.option("--ticker", default="", help="Target ticker (required for watchlist-brief)")
@click.option("--provider", default="", help="Override AI provider (anthropic | openai | ollama)")
@click.option("--model", default="", help="Override model (e.g. gpt-4o-mini, llama3.1)")
@click.option("--refresh", is_flag=True, help="Force-refresh market data before running skill")
@click.pass_context
def ai_cmd(
    ctx: click.Context,
    skill_name: str,
    ticker: str,
    provider: str,
    model: str,
    refresh: bool,
) -> None:
    """Run an LLM-powered skill against your portfolio data.

    \b
    Available skills:
      portfolio-narrative   Plain-English portfolio health briefing
      watchlist-brief       Research brief for a watchlist ticker (needs --ticker)

    \b
    Examples:
      divvy ai portfolio-narrative
      divvy ai watchlist-brief --ticker POWERGRID
      divvy ai portfolio-narrative --provider openai --model gpt-4o-mini
      divvy ai portfolio-narrative --provider ollama --model llama3.1
    """
    cfg: Config = ctx.obj["config"]

    # Normalise: portfolio-narrative → portfolio_narrative
    skill_key = skill_name.replace("-", "_").lower()
    skill_dir = _SKILLS_ROOT / skill_key

    if not skill_dir.exists():
        available = _available_skills()
        click.echo(f"Error: skill '{skill_name}' not found.", err=True)
        if available:
            click.echo(f"Available skills: {', '.join(available)}", err=True)
        raise click.Abort()

    # Load skill definition
    try:
        skill = load_skill(skill_dir)
    except FileNotFoundError as exc:
        click.echo(f"Error loading skill: {exc}", err=True)
        raise click.Abort()

    # Gather context by importing the skill's context.py
    try:
        ctx_module = import_module(f"dividend.skills.{skill_key}.context")
    except ModuleNotFoundError:
        click.echo(
            f"Error: dividend/skills/{skill_key}/context.py not found.", err=True
        )
        raise click.Abort()

    click.echo(f"Preparing context for '{skill_name}'…")
    try:
        context = ctx_module.gather(cfg, ticker=ticker, refresh=refresh)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()

    # Render prompt
    try:
        prompt = render_prompt(skill, context)
    except ValueError as exc:
        click.echo(f"Prompt error: {exc}", err=True)
        raise click.Abort()

    # Resolve provider + model (CLI flags override config)
    _provider = provider or cfg.ai.provider
    _model = model or cfg.ai.model
    _ollama_url = cfg.ai.ollama_base_url

    click.echo(f"Running '{skill.name}' via {_provider}/{_model}…\n")
    click.echo("─" * 60)

    try:
        runner = create_runner(
            _provider, _model,
            ollama_base_url=_ollama_url,  # ignored by non-ollama providers
        )
        response = runner.complete(
            prompt=prompt,
            system=skill.system_prompt,
            max_tokens=skill.max_tokens,
        )
    except ImportError as exc:
        click.echo(f"\nMissing dependency: {exc}", err=True)
        raise click.Abort()
    except Exception as exc:
        click.echo(f"\nLLM call failed: {exc}", err=True)
        raise click.Abort()

    click.echo(response.content)
    click.echo("\n" + "─" * 60)

    if response.input_tokens is not None and response.output_tokens is not None:
        click.echo(
            f"  {response.input_tokens} tokens in / "
            f"{response.output_tokens} tokens out  "
            f"[{_provider}/{_model}]",
            err=True,
        )
