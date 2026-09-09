"""CLI entry point for the momentum screener (command: momo)."""
from __future__ import annotations

from pathlib import Path

import click

from .commands.backtest import backtest_cmd
from .commands.fetch import fetch_cmd
from .commands.run import run_cmd
from .config import load_config


@click.group()
@click.option(
    "--config-file",
    default="momentum/config.yaml",
    type=click.Path(),
    show_default=True,
    help="Path to momentum config YAML (relative to repo root).",
)
@click.pass_context
def cli(ctx: click.Context, config_file: str) -> None:
    """Momo — NSE monthly momentum screener."""
    ctx.ensure_object(dict)
    cfg = load_config(Path(config_file))
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    ctx.obj["config"] = cfg


cli.add_command(fetch_cmd)
cli.add_command(backtest_cmd)
cli.add_command(run_cmd)


def main() -> None:
    """Entry point declared in pyproject.toml."""
    cli()
