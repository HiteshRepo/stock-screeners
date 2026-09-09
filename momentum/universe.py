"""Universe management — load/save the set of NSE symbols to score."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UniverseEntry:
    symbol: str
    company_name: str
    sector: str
    index_name: str  # e.g. NIFTY500


_HEADERS = ["symbol", "company_name", "sector", "index_name"]


def load_universe(path: Path) -> list[UniverseEntry]:
    """Load universe entries from a CSV file. Returns [] if file is missing."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        entries: list[UniverseEntry] = []
        for row in reader:
            sym = row.get("symbol", "").strip().upper()
            if not sym:
                continue
            entries.append(UniverseEntry(
                symbol=sym,
                company_name=row.get("company_name", "").strip(),
                sector=row.get("sector", "").strip(),
                index_name=row.get("index_name", "NIFTY500").strip(),
            ))
    return entries


def get_symbols(path: Path) -> list[str]:
    """Return the deduplicated list of symbols from the universe file."""
    seen: set[str] = set()
    result: list[str] = []
    for e in load_universe(path):
        if e.symbol not in seen:
            seen.add(e.symbol)
            result.append(e.symbol)
    return result


def save_universe(path: Path, entries: list[UniverseEntry]) -> None:
    """Write universe entries to a CSV file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADERS)
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "symbol": e.symbol,
                "company_name": e.company_name,
                "sector": e.sector,
                "index_name": e.index_name,
            })
