"""
dividend.cli — Click entry point for the divvy CLI.

Run from repo root:
    divvy --help
    divvy status
    divvy buy --ticker HDFCBANK --shares 10 --price 1650

Or without installing:
    python -m dividend.cli --help
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from .config import load_config
from .md_io import ensure_data_files
from .commands.buy import buy_cmd
from .commands.sell import sell_cmd
from .commands.status import status_cmd
from .commands.review import review_cmd
from .commands.recommend import recommend_cmd
from .commands.ai import ai_cmd


@click.group()
@click.option(
    "--config-file",
    default="dividend/config.yaml",
    type=click.Path(),
    show_default=True,
    help="Path to config.yaml (relative to repo root)",
)
@click.pass_context
def cli(ctx: click.Context, config_file: str) -> None:
    """Divvy — Indian dividend portfolio manager.

    \b
    Tracks holdings in local markdown files that stay readable in
    GitHub diffs. All commands are safe to run any time; only `buy`
    and `sell` modify portfolio.md / transactions.md.

    \b
    Run from the repo root so relative paths in config.yaml resolve
    correctly.
    """
    ctx.ensure_object(dict)
    cfg = load_config(Path(config_file))
    ensure_data_files(cfg.portfolio_path, cfg.watchlist_path, cfg.transactions_path)
    ctx.obj["config"] = cfg


cli.add_command(buy_cmd)
cli.add_command(sell_cmd)
cli.add_command(status_cmd)
cli.add_command(review_cmd)
cli.add_command(recommend_cmd)
cli.add_command(ai_cmd)


def main() -> None:
    """Entry point declared in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
