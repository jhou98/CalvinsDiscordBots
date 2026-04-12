"""
Tests for helpers/validation_utils.py — general-purpose validation utilities.
"""

from src.helpers.validation_utils import is_numeric, validate_phone

# ---------------------------------------------------------------------------
# is_numeric
# ---------------------------------------------------------------------------


class TestIsNumeric:
    def test_integer_string(self):
        assert is_numeric("3") is True

    def test_float_string(self):
        assert is_numeric("2.5") is True

    def test_negative(self):
        assert is_numeric("-1") is True

    def test_word(self):
        assert is_numeric("lots") is False

    def test_empty(self):
        assert is_numeric("") is False

    def test_mixed(self):
        assert is_numeric("3boxes") is False


# ---------------------------------------------------------------------------
# validate_phone
# ---------------------------------------------------------------------------


class TestValidatePhone:
    def test_standard_format(self):
        assert validate_phone("555-867-5309") == "555-867-5309"

    def test_with_parens(self):
        assert validate_phone("(555) 867-5309") == "(555) 867-5309"

    def test_plain_digits(self):
        assert validate_phone("5558675309") == "5558675309"

    def test_with_country_code(self):
        assert validate_phone("+1 555 867 5309") == "+1 555 867 5309"

    def test_with_dots(self):
        assert validate_phone("555.867.5309") == "555.867.5309"

    def test_seven_digits_minimum(self):
        assert validate_phone("5551234") == "5551234"

    def test_too_few_digits(self):
        assert validate_phone("123") is None

    def test_too_many_digits(self):
        assert validate_phone("1234567890123456") is None

    def test_empty_string(self):
        assert validate_phone("") is None

    def test_whitespace_only(self):
        assert validate_phone("   ") is None

    def test_no_digits(self):
        assert validate_phone("call me") is None

    def test_strips_whitespace(self):
        assert validate_phone("  555-867-5309  ") == "555-867-5309"
