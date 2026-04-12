"""
General-purpose validation utilities.
"""


def is_numeric(value: str) -> bool:
    """Return True if value can be parsed as a number."""
    try:
        float(value)
        return True
    except ValueError:
        return False
