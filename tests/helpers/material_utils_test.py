"""
Tests for helpers/material_utils.py — material parsing, formatting, and validation.
"""

from src.helpers.material_utils import format_materials, parse_materials, validate_materials

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
# validate_materials
# ---------------------------------------------------------------------------


class TestValidateMaterials:
    def test_valid_input_returns_list_and_none(self):
        materials, error = validate_materials("Breaker - 3\nWire - 2")
        assert materials == [("Breaker", "3"), ("Wire", "2")]
        assert error is None

    def test_missing_separator_returns_error(self):
        materials, error = validate_materials("BadLine")
        assert materials == []
        assert error is not None
        assert "Missing quantity" in error

    def test_non_numeric_quantity_returns_error(self):
        materials, error = validate_materials("Breaker - lots")
        assert materials == []
        assert error is not None
        assert "Non-numeric" in error

    def test_mixed_errors_returns_all(self):
        materials, error = validate_materials("BadLine\nBreaker - lots")
        assert materials == []
        assert "Missing quantity" in error
        assert "Non-numeric" in error

    def test_empty_string(self):
        materials, error = validate_materials("")
        assert materials == []
        assert error is None
