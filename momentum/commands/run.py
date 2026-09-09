"""momentum run — monthly live scoring + diff against current holdings."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import click

from ..config import MomentumConfig
from ..md_io import MomentumHolding, read_holdings, write_holdings, write_run_log
from ..scoring import MomentumScore, score_universe
from ..store import PriceStore
from ..universe import get_symbols


def _config_summary(cfg: MomentumConfig) -> str:
    s = cfg.scoring
    secondary = []
    if s.use_pct_positive_days:
        secondary.append("pct-pos-days")
    if s.use_dist_from_52w_high:
        secondary.append("dist-52w-high")
    if s.use_sharpe_ratio:
        secondary.append("sharpe")
    suffix = f", secondary=[{', '.join(secondary)}]" if secondary else ""
    return (
        f"top_n={s.top_n}, "
        f"lookback={s.lookback_months}m, "
        f"skip={s.skip_recent_months}m, "
        f"min_tv=₹{s.min_daily_traded_value_cr:.0f}cr"
        f"{suffix}"
    )


def _ranked_table_lines(scores: list[MomentumScore]) -> list[str]:
    header = "| Rank | Symbol | Momentum (12M) | Avg TV (₹Cr) | Score | Flag |"
    sep = "|------|--------|---------------|-------------|-------|------|"
    rows = [header, sep]
    for s in scores:
        flag = "⚠ CA" if s.has_corporate_action else ""
        rows.append(
            f"| {s.rank} | {s.symbol} | {s.momentum_return * 100:+.1f}% "
            f"| {s.avg_traded_value_cr:.1f} | {s.composite_score:.3f} | {flag} |"
        )
    return rows


def _diff_lines(
    top_symbols: list[str],
    holdings: list[MomentumHolding],
) -> list[str]:
    held = {h.symbol for h in holdings}
    top_set = set(top_symbols)

    adds = sorted(top_set - held)
    holds = sorted(top_set & held)
    drops = sorted(held - top_set)

    lines: list[str] = []

    lines.append(f"### ADD ({len(adds)} new positions)")
    if adds:
        lines += ["| Symbol |", "|--------|"] + [f"| {s} |" for s in adds]
    else:
        lines.append("_No new entries._")

    lines += ["", f"### HOLD ({len(holds)} retained)"]
    if holds:
        lines += ["| Symbol |", "|--------|"] + [f"| {s} |" for s in holds]
    else:
        lines.append("_None retained._")

    lines += ["", f"### DROP ({len(drops)} to exit)"]
    if drops:
        lines += ["| Symbol |", "|--------|"] + [f"| {s} |" for s in drops]
    else:
        lines.append("_No exits._")

    return lines


def _send_whatsapp_notification(
    cfg: MomentumConfig,
    scores: list[MomentumScore],
    run_date: date,
) -> None:
    if not cfg.whatsapp_api_key or not cfg.whatsapp_phone:
        click.echo("WhatsApp: skipped (api_key or phone not configured).")
        return
    top5 = scores[:5]
    msg_parts = [f"Momentum Run {run_date}", "Top 5:"]
    for s in top5:
        msg_parts.append(f"{s.rank}. {s.symbol} {s.momentum_return * 100:+.0f}%")
    msg = "%0A".join(msg_parts)
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={cfg.whatsapp_phone}&text={msg}&apikey={cfg.whatsapp_api_key}"
    )
    try:
        import requests as _req
        _req.get(url, timeout=10)
        click.echo("WhatsApp notification sent.")
    except Exception as e:
        click.echo(f"WhatsApp notification failed: {e}")


@click.command("run")
@click.option("--top-n", default=None, type=int, help="Override portfolio size.")
@click.option(
    "--as-of",
    default=None,
    metavar="YYYY-MM-DD",
    help="Score as of this date.  Defaults to today.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print output but do not update holdings file or write run log.",
)
@click.option(
    "--notify",
    is_flag=True,
    default=False,
    help="Send WhatsApp notification on completion (requires whatsapp config).",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    top_n: int | None,
    as_of: str | None,
    dry_run: bool,
    notify: bool,
) -> None:
    """
    Run the monthly momentum screener and output ADD / HOLD / DROP diff.

    Run this once a month after market close.  It scores the Nifty 500
    universe, computes the diff vs your current holdings, and (unless
    --dry-run) writes a dated log to momentum/data/runs/ and updates
    the holdings file.

    Example:

      momo run                       # live run, updates files
      momo run --dry-run             # preview only
      momo run --as-of 2025-08-29    # back-dated run (for testing)
    """
    cfg: MomentumConfig = ctx.obj["config"]

    try:
        run_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as e:
        raise click.BadParameter(str(e))

    scoring = cfg.scoring
    if top_n is not None:
        scoring = replace(scoring, top_n=top_n)

    symbols = get_symbols(cfg.universe_path)
    if not symbols:
        raise click.UsageError(
            f"Universe file empty or missing: {cfg.universe_path}\n"
            "Populate momentum/data/nifty500.csv with NSE symbols first."
        )

    store = PriceStore(cfg.db_path)
    click.echo(f"Scoring {len(symbols)} symbols as of {run_date} …")
    scores = score_universe(store, symbols, run_date, scoring)
    store.close()

    if not scores:
        click.echo(
            "No symbols scored.  Check that price data covers the required period:\n"
            f"  Need ~{scoring.lookback_months + scoring.skip_recent_months + 1} months "
            f"of history ending {run_date}.\n"
            "  Run: momo fetch --start <date> --end <date>"
        )
        return

    top_scores = scores[: scoring.top_n]
    top_symbols = [s.symbol for s in top_scores]
    holdings = read_holdings(cfg.holdings_path)

    ranked_lines = _ranked_table_lines(top_scores)
    diff_lines = _diff_lines(top_symbols, holdings)

    click.echo()
    for line in ranked_lines:
        click.echo(line)
    click.echo()
    for line in diff_lines:
        click.echo(line)
    click.echo()

    if not dry_run:
        new_holdings = [
            MomentumHolding(
                symbol=s.symbol,
                added_date=run_date.isoformat(),
                added_rank=s.rank,
                notes="",
            )
            for s in top_scores
        ]
        write_holdings(cfg.holdings_path, new_holdings)
        log_path = write_run_log(
            cfg.runs_dir,
            run_date,
            ranked_lines,
            diff_lines,
            _config_summary(cfg),
        )
        click.echo(f"Holdings updated : {cfg.holdings_path}")
        click.echo(f"Run log written  : {log_path}")
    else:
        click.echo("(dry-run: no files written)")

    if notify and not dry_run:
        _send_whatsapp_notification(cfg, scores, run_date)
