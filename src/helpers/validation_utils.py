"""
General-purpose validation utilities.
"""

import re


def is_numeric(value: str) -> bool:
    """Return True if value can be parsed as a number."""
    try:
        float(value)
        return True
    except ValueError:
        return False


def validate_phone(raw: str) -> str | None:
    """
    Basic phone validation.
    Accepts digits, spaces, dashes, parens, dots, and leading +.
    Requires 7–15 digits after stripping non-digit characters.
    Returns the stripped string on success, None on failure.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    digits = re.sub(r"\D", "", stripped)
    if len(digits) < 7 or len(digits) > 15:
        return None
    return stripped
