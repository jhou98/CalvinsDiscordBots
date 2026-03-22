"""
Tests for helpers/helpers.py — pure helper functions.
"""

import re
from unittest.mock import MagicMock

import discord
import pytest

from src.helpers.helpers import (
    build_change_order_embed,
    discord_timestamp,
    format_materials,
    format_plain_text,
    parse_materials,
    resolve_date,
)

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


# ---------------------------------------------------------------------------
# parse_materials
# ---------------------------------------------------------------------------


class TestParseMaterials:
    def test_single_valid_line(self):
        materials, errors = parse_materials("20A Breaker - 3")
        assert materials == [("20A Breaker", "3")]
        assert errors == []

    def test_multiple_valid_lines(self):
        raw = "20A Breaker - 3\n12 AWG Wire - 2\nJunction Box - 5"
        materials, errors = parse_materials(raw)
        assert len(materials) == 3
        assert materials[0] == ("20A Breaker", "3")
        assert materials[2] == ("Junction Box", "5")

    def test_invalid_line_captured_in_errors(self):
        materials, errors = parse_materials("BadLine")
        assert materials == []
        assert errors == ["BadLine"]

    def test_mixed_valid_and_invalid(self):
        raw = "Good Item - 2\nBadLine\nAnother Good - 10"
        materials, errors = parse_materials(raw)
        assert len(materials) == 2
        assert errors == ["BadLine"]

    def test_empty_string(self):
        materials, errors = parse_materials("")
        assert materials == []
        assert errors == []

    def test_extra_whitespace_trimmed(self):
        materials, _ = parse_materials("  Widget  -  7  ")
        assert materials == [("Widget", "7")]

    def test_dash_in_item_name(self):
        """Only the first ' - ' should be used as the separator."""
        materials, errors = parse_materials("12-2 Wire - 5")
        assert materials == [("12-2 Wire", "5")]
        assert errors == []

    def test_blank_lines_ignored(self):
        raw = "Item A - 1\n\n\nItem B - 2"
        materials, _ = parse_materials(raw)
        assert len(materials) == 2


# ---------------------------------------------------------------------------
# format_materials
# ---------------------------------------------------------------------------


class TestFormatMaterials:
    def test_empty_list(self):
        assert format_materials([]) == "_No materials listed._"

    def test_single_item(self):
        result = format_materials([("Breaker", "3")])
        assert "`Breaker`" in result
        assert "**3**" in result

    def test_multiple_items(self):
        result = format_materials([("A", "1"), ("B", "2")])
        assert "`A`" in result
        assert "`B`" in result


# ---------------------------------------------------------------------------
# build_change_order_embed
# ---------------------------------------------------------------------------


class TestBuildChangeOrderEmbed:
    def _make_user(self):
        user = MagicMock(spec=discord.Member)
        user.mention = "<@1>"
        return user

    def test_returns_embed(self):
        embed = build_change_order_embed(
            user=self._make_user(),
            date="01/01/2025",
            submitted_at="<t:1234567890:F>",
            scope="Install new panel",
            material_list=[("Breaker", "2")],
        )
        assert isinstance(embed, discord.Embed)

    def test_default_title(self):
        embed = build_change_order_embed(
            user=self._make_user(),
            date="01/01/2025",
            submitted_at="<t:1234567890:F>",
            scope="Scope",
            material_list=[],
        )
        assert embed.title == "📋 Change Order"

    def test_custom_title_and_color(self):
        embed = build_change_order_embed(
            user=self._make_user(),
            date="01/01/2025",
            submitted_at="<t:1234567890:F>",
            scope="Scope",
            material_list=[],
            title="✅ Done",
            color=discord.Color.green(),
        )
        assert embed.title == "✅ Done"
        assert embed.color == discord.Color.green()

    def test_material_count_in_field_name(self):
        embed = build_change_order_embed(
            user=self._make_user(),
            date="01/01/2025",
            submitted_at="<t:1234567890:F>",
            scope="Scope",
            material_list=[("A", "1"), ("B", "2")],
        )
        field_names = [f.name for f in embed.fields]
        assert any("2 items" in name for name in field_names)

    def test_singular_material_count(self):
        embed = build_change_order_embed(
            user=self._make_user(),
            date="01/01/2025",
            submitted_at="<t:1234567890:F>",
            scope="Scope",
            material_list=[("A", "1")],
        )
        field_names = [f.name for f in embed.fields]
        assert any("1 item" in name and "items" not in name for name in field_names)


class TestFormatPlainText:
    def _make_user(self, display_name="Jack"):
        user = MagicMock(spec=discord.Member)
        user.display_name = display_name
        return user

    def test_contains_date(self):
        result = format_plain_text(self._make_user(), "01/01/2025", "Install panel", [])
        assert "01/01/2025" in result

    def test_contains_display_name(self):
        result = format_plain_text(self._make_user("Jack"), "01/01/2025", "Install panel", [])
        assert "Jack" in result

    def test_contains_scope(self):
        result = format_plain_text(self._make_user(), "01/01/2025", "Run new circuits", [])
        assert "Run new circuits" in result

    def test_materials_formatted_correctly(self):
        result = format_plain_text(self._make_user(), "01/01/2025", "Scope", [("Breaker", "3")])
        assert "Breaker - 3" in result

    def test_empty_materials_shows_placeholder(self):
        result = format_plain_text(self._make_user(), "01/01/2025", "Scope", [])
        assert "No materials listed." in result

    def test_multiple_materials(self):
        materials = [("Breaker", "3"), ("12 AWG Wire", "2")]
        result = format_plain_text(self._make_user(), "01/01/2025", "Scope", materials)
        assert "Breaker - 3" in result
        assert "12 AWG Wire - 2" in result
