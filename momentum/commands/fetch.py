"""momentum fetch — download NSE bhavcopy data into the local SQLite store."""
from __future__ import annotations

from datetime import date

import click

from ..bhavcopy import fetch_range
from ..config import MomentumConfig
from ..store import PriceStore


@click.command("fetch")
@click.option(
    "--start",
    required=True,
    metavar="YYYY-MM-DD",
    help="Start date (inclusive).",
)
@click.option(
    "--end",
    default=None,
    metavar="YYYY-MM-DD",
    help="End date (inclusive).  Defaults to today.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-download dates that are already cached.",
)
@click.pass_context
def fetch_cmd(ctx: click.Context, start: str, end: str | None, force: bool) -> None:
    """
    Download NSE equity bhavcopy data for a date range.

    Data is stored in the local SQLite price store (see db_path in config).
    Only missing dates are downloaded by default; use --force to re-fetch cached dates.

    Example — backfill 5 years of history:

      momo fetch --start 2020-01-01 --end 2024-12-31

    NSE holidays return HTTP 404 and are skipped automatically.
    Weekends are skipped without making any network request.
    """
    cfg: MomentumConfig = ctx.obj["config"]

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        raise click.BadParameter(str(e))

    if start_date > end_date:
        raise click.UsageError("--start must be on or before --end")

    store = PriceStore(cfg.db_path)
    click.echo(f"Fetching bhavcopy:  {start_date}  →  {end_date}")
    click.echo(f"Store: {cfg.db_path}")
    click.echo()

    def _progress(d: date, msg: str) -> None:
        click.echo(f"  {d.isoformat()}  {msg}")

    summary = fetch_range(start_date, end_date, store, on_progress=_progress)
    store.close()

    click.echo()
    click.echo(
        f"Done.  fetched={summary['fetched']}  "
        f"cached={summary['cached']}  "
        f"errors={len(summary['errors'])}"
    )
    if summary["errors"]:
        click.echo("\nErrors:")
        for d, err in summary["errors"]:
            click.echo(f"  {d}  {err}")
