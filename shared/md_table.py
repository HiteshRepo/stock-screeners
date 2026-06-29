"""
shared.md_table — generic markdown table parser and formatter.

Used by all tools (dividend, trade, …). Keeps domain-specific models
out of the parsing layer so each tool imports only what it needs.
"""
from __future__ import annotations

import re


def parse_table(text: str) -> list[dict[str, str]]:
    """
    Parse the first markdown table found in *text*.

    Returns a list of row dicts keyed by the header row's cell values.
    Handles:
    - Extra whitespace in cells
    - Hand-edited column widths
    - Missing or extra trailing pipes
    - Empty data rows (skipped)
    """
    lines = text.splitlines()
    headers: list[str] | None = None
    rows: list[dict[str, str]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if headers is None:
            headers = cells
            continue

        # Separator row — e.g. |---|:---:|
        # Require at least one non-empty cell so that all-empty rows (|  |  |)
        # are not mistakenly matched (all() on empty iterator is True).
        non_empty = [c for c in cells if c]
        if non_empty and all(re.fullmatch(r":?-+:?", c) for c in non_empty):
            continue

        # Pad or trim to match header count
        while len(cells) < len(headers):
            cells.append("")
        row = dict(zip(headers, cells[: len(headers)]))
        rows.append(row)

    return rows


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """
    Format *headers* and *rows* as a clean, padded markdown table.

    Column widths auto-fit to the widest value in each column.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    def fmt_row(cells: list[str]) -> str:
        parts = [f" {str(c):<{widths[i]}} " for i, c in enumerate(cells)]
        return "|" + "|".join(parts) + "|"

    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([fmt_row(headers), sep] + [fmt_row(row) for row in rows])
