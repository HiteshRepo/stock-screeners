"""Tests for shared.md_table — generic markdown table parse/format."""
import pytest
from shared.md_table import parse_table, format_table


# ---------------------------------------------------------------------------
# parse_table
# ---------------------------------------------------------------------------

class TestParseTable:
    def test_standard_table(self):
        text = (
            "| A | B | C |\n"
            "|---|---|---|\n"
            "| 1 | 2 | 3 |\n"
            "| 4 | 5 | 6 |\n"
        )
        rows = parse_table(text)
        assert rows == [
            {"A": "1", "B": "2", "C": "3"},
            {"A": "4", "B": "5", "C": "6"},
        ]

    def test_extra_whitespace_in_cells(self):
        text = (
            "|  A  |  B  |\n"
            "|-----|-----|\n"
            "|  hello  |  world  |\n"
        )
        rows = parse_table(text)
        assert rows[0] == {"A": "hello", "B": "world"}

    def test_missing_trailing_pipe(self):
        text = "| A | B\n|---|---\n| 1 | 2"
        rows = parse_table(text)
        assert rows[0]["A"] == "1"
        assert rows[0]["B"] == "2"

    def test_empty_table_header_only(self):
        text = "| A | B |\n|---|---|\n"
        rows = parse_table(text)
        assert rows == []

    def test_empty_cells(self):
        text = "| A | B |\n|---|---|\n|  |  |\n"
        rows = parse_table(text)
        assert rows[0] == {"A": "", "B": ""}

    def test_skips_non_table_lines(self):
        text = "# Heading\n\nSome text.\n\n| X |\n|---|\n| v |\n"
        rows = parse_table(text)
        assert rows == [{"X": "v"}]

    def test_unicode_in_headers(self):
        text = "| Price (₹) |\n|----------|\n| 1650.00 |\n"
        rows = parse_table(text)
        assert rows[0]["Price (₹)"] == "1650.00"

    def test_fewer_cells_than_headers_padded(self):
        text = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n"
        rows = parse_table(text)
        assert rows[0] == {"A": "1", "B": "2", "C": ""}

    def test_no_table_in_text(self):
        rows = parse_table("Just a heading\n\nAnd some prose.")
        assert rows == []


# ---------------------------------------------------------------------------
# format_table
# ---------------------------------------------------------------------------

class TestFormatTable:
    def test_basic_format(self):
        headers = ["A", "B"]
        rows = [["1", "2"], ["33", "44"]]
        result = format_table(headers, rows)
        lines = result.splitlines()
        assert lines[0].startswith("|")
        assert "---" in lines[1]  # separator row
        assert len(lines) == 4    # header + sep + 2 data rows

    def test_column_width_auto_fits(self):
        headers = ["X"]
        rows = [["short"], ["a much longer value"]]
        result = format_table(headers, rows)
        # All rows should have the same total width
        line_lengths = [len(line) for line in result.splitlines()]
        assert len(set(line_lengths)) == 1

    def test_roundtrip(self):
        headers = ["Ticker", "Price (₹)"]
        rows = [["HDFCBANK", "1650.00"], ["ITC", "400.50"]]
        table_text = format_table(headers, rows)
        parsed = parse_table(table_text)
        assert parsed[0]["Ticker"] == "HDFCBANK"
        assert parsed[1]["Price (₹)"] == "400.50"
