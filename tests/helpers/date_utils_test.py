"""
Tests for helpers/date_utils.py — date and timestamp utilities.
"""

import re

import pytest

from src.helpers.date_utils import discord_timestamp, resolve_date

# ---------------------------------------------------------------------------
# resolve_date
# ---------------------------------------------------------------------------


class TestResolveDate:
    def test_returns_provided_date(self):
        assert resolve_date("12/25/2024") == "12/25/2024"

    def test_strips_whitespace(self):
        assert resolve_date("  01/01/2025  ") == "01/01/2025"

    def test_empty_string_returns_today(self):
        result = resolve_date("")
        # Should look like MM/DD/YYYY
        assert re.match(r"\d{2}/\d{2}/\d{4}", result)

    def test_whitespace_only_returns_today(self):
        result = resolve_date("   ")
        assert re.match(r"\d{2}/\d{2}/\d{4}", result)

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError):
            resolve_date("2026-03-15")

    def test_error_message_contains_bad_value(self):
        with pytest.raises(ValueError, match="2026-03-15"):
            resolve_date("2026-03-15")

    def test_error_message_contains_expected_format(self):
        with pytest.raises(ValueError, match="MM/DD/YYYY"):
            resolve_date("2026-03-15")

    @pytest.mark.parametrize(
        "bad_input",
        [
            "2026-03-15",  # ISO format
            "15/03/2026",  # DD/MM/YYYY
            "03/15/26",  # two-digit year
            "03-15-2026",  # dashes instead of slashes
            "13/01/2026",  # invalid month
            "03/32/2026",  # invalid day
            "notadate",  # garbage
        ],
    )
    def test_invalid_formats_raise(self, bad_input):
        with pytest.raises(ValueError):
            resolve_date(bad_input)


# ---------------------------------------------------------------------------
# discord_timestamp
# ---------------------------------------------------------------------------


class TestDiscordTimestamp:
    def test_format(self):
        ts = discord_timestamp()
        # Expected: <t:1234567890:F>
        assert re.match(r"<t:\d+:F>", ts)

    def test_unix_value_is_recent(self):
        import time

        ts = discord_timestamp()
        unix = int(re.search(r"\d+", ts).group())
        assert abs(unix - int(time.time())) < 5
