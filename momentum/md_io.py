"""Markdown I/O for momentum holdings and dated run logs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shared.md_table import format_table, parse_table


# ---------------------------------------------------------------------------
# Holdings — the current momentum portfolio
# ---------------------------------------------------------------------------

@dataclass
class MomentumHolding:
    symbol: str
    added_date: str    # YYYY-MM-DD
    added_rank: int
    notes: str


_HOLDINGS_HEADERS = ["Symbol", "Added Date", "Added Rank", "Notes"]

_HOLDINGS_TEMPLATE = """\
# Momentum Holdings

{table}
"""


def read_holdings(path: Path) -> list[MomentumHolding]:
    """Return holdings from the markdown file, or [] if the file is missing."""
    if not path.exists():
        return []
    rows = parse_table(path.read_text(encoding="utf-8"))
    result: list[MomentumHolding] = []
    for row in rows:
        sym = row.get("Symbol", "").strip()
        if not sym:
            continue
        try:
            result.append(MomentumHolding(
                symbol=sym,
                added_date=row.get("Added Date", "").strip(),
                added_rank=int(row.get("Added Rank", "0").strip() or 0),
                notes=row.get("Notes", "").strip(),
            ))
        except (ValueError, KeyError):
            continue
    return result


def write_holdings(path: Path, holdings: list[MomentumHolding]) -> None:
    """Overwrite the holdings markdown file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [h.symbol, h.added_date, str(h.added_rank), h.notes]
        for h in holdings
    ]
    table = format_table(_HOLDINGS_HEADERS, rows)
    path.write_text(_HOLDINGS_TEMPLATE.format(table=table), encoding="utf-8")


# ---------------------------------------------------------------------------
# Run log — dated snapshot written each monthly run
# ---------------------------------------------------------------------------

def write_run_log(
    runs_dir: Path,
    run_date: date,
    ranked_lines: list[str],
    diff_lines: list[str],
    config_summary: str,
) -> Path:
    """
    Write a dated run log to runs_dir/YYYY-MM-DD.md and return its path.
    Creates runs_dir if it doesn't exist.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = runs_dir / f"{run_date.isoformat()}.md"

    content = "\n".join([
        f"# Momentum Run — {run_date.isoformat()}",
        "",
        f"**Config**: {config_summary}",
        "",
        "## Ranked List",
        "",
        *ranked_lines,
        "",
        "## Diff vs Holdings",
        "",
        *diff_lines,
        "",
    ])
    out_path.write_text(content, encoding="utf-8")
    return out_path
