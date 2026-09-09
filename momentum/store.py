"""SQLite-backed OHLCV warehouse for NSE equity data."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


@dataclass
class DailyBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    traded_value_cr: float   # ₹ crore
    series: str = "EQ"


class PriceStore:
    """
    SQLite OHLCV store for NSE bhavcopy data.

    Schema:
    - daily_prices(symbol, date PK, open, high, low, close, volume, traded_value_cr, series)
    - fetched_dates(date PK, rows_eq, fetched_at)  — tracks which bhavcopy dates are loaded
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS daily_prices (
            symbol          TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            volume          REAL,
            traded_value_cr REAL,
            series          TEXT    DEFAULT 'EQ',
            PRIMARY KEY (symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_dp_date   ON daily_prices(date);
        CREATE INDEX IF NOT EXISTS idx_dp_symbol ON daily_prices(symbol);

        CREATE TABLE IF NOT EXISTS fetched_dates (
            date        TEXT PRIMARY KEY,
            rows_eq     INTEGER,
            fetched_at  TEXT
        );
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_daily(self, rows: list[DailyBar]) -> int:
        """
        Insert rows, silently ignoring (symbol, date) duplicates.
        Returns the number of rows in the input (not the actual inserted count,
        since sqlite OR IGNORE suppresses the rowcount).
        """
        data = [
            (r.symbol, r.date.isoformat(), r.open, r.high,
             r.low, r.close, r.volume, r.traded_value_cr, r.series)
            for r in rows
        ]
        self._conn.executemany(
            """INSERT OR IGNORE INTO daily_prices
               (symbol, date, open, high, low, close, volume, traded_value_cr, series)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        self._conn.commit()
        return len(data)

    def mark_date_fetched(self, d: date, rows_eq: int) -> None:
        """Record that bhavcopy for d has been fetched and stored."""
        self._conn.execute(
            "INSERT OR REPLACE INTO fetched_dates(date, rows_eq, fetched_at) "
            "VALUES(?, ?, datetime('now'))",
            (d.isoformat(), rows_eq),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def has_date(self, d: date) -> bool:
        """True if the bhavcopy for this date has already been stored."""
        cur = self._conn.execute(
            "SELECT 1 FROM fetched_dates WHERE date = ?", (d.isoformat(),)
        )
        return cur.fetchone() is not None

    def get_close_prices(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Pivot table of EQ-series close prices.
        Index = date strings (YYYY-MM-DD), columns = symbol, values = close.
        """
        if not symbols:
            return pd.DataFrame()
        ph = ",".join("?" * len(symbols))
        df = pd.read_sql(
            f"""SELECT symbol, date, close
                FROM daily_prices
                WHERE symbol IN ({ph})
                  AND date BETWEEN ? AND ?
                  AND series = 'EQ'
                ORDER BY date""",
            self._conn,
            params=[*symbols, start_date.isoformat(), end_date.isoformat()],
        )
        if df.empty:
            return pd.DataFrame()
        return df.pivot(index="date", columns="symbol", values="close")

    def get_avg_traded_value_cr(
        self,
        symbols: list[str],
        as_of_date: date,
        lookback_days: int = 60,
    ) -> dict[str, float]:
        """
        Average daily traded value (₹ crore) for each symbol over approximately
        the last lookback_days trading days (implemented as a calendar-day window
        with a 2× buffer to account for weekends and holidays).
        """
        if not symbols:
            return {}
        # 2× buffer: 60 trading days ≈ 85 calendar days
        window_start = (as_of_date - timedelta(days=lookback_days * 2)).isoformat()
        ph = ",".join("?" * len(symbols))
        df = pd.read_sql(
            f"""SELECT symbol, AVG(traded_value_cr) AS avg_tv
                FROM daily_prices
                WHERE symbol IN ({ph})
                  AND date BETWEEN ? AND ?
                  AND series = 'EQ'
                GROUP BY symbol""",
            self._conn,
            params=[*symbols, window_start, as_of_date.isoformat()],
        )
        if df.empty:
            return {}
        return dict(zip(df["symbol"], df["avg_tv"].fillna(0.0)))

    def get_available_dates(self, start_date: date, end_date: date) -> list[date]:
        """All dates recorded in fetched_dates within [start_date, end_date]."""
        cur = self._conn.execute(
            "SELECT date FROM fetched_dates WHERE date BETWEEN ? AND ? ORDER BY date",
            (start_date.isoformat(), end_date.isoformat()),
        )
        return [date.fromisoformat(row["date"]) for row in cur.fetchall()]

    def get_symbols_with_min_history(
        self, min_days: int, as_of_date: date
    ) -> list[str]:
        """Symbols with at least min_days of EQ rows on or before as_of_date."""
        cur = self._conn.execute(
            """SELECT symbol
               FROM daily_prices
               WHERE date <= ? AND series = 'EQ'
               GROUP BY symbol
               HAVING COUNT(*) >= ?""",
            (as_of_date.isoformat(), min_days),
        )
        return [row["symbol"] for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
