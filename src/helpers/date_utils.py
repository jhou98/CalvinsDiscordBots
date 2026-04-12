"""
Date and timestamp utilities.
"""

from datetime import UTC, datetime


def resolve_date(raw: str) -> str:
    """
    Return raw date string if provided and valid (MM/DD/YYYY), otherwise today's date.
    Raises ValueError if a non-empty string is provided in the wrong format.
    """
    if not raw.strip():
        return datetime.today().strftime("%m/%d/%Y")
    try:
        datetime.strptime(raw.strip(), "%m/%d/%Y")
    except ValueError as e:
        raise ValueError(
            f"Invalid date format `{raw.strip()}` — expected MM/DD/YYYY (e.g. `03/15/2026`)."
        ) from e

    return raw.strip()


def discord_timestamp() -> str:
    """Return a Discord-formatted timestamp that renders in each user's local timezone."""
    unix_now = int(datetime.now(UTC).timestamp())
    return f"<t:{unix_now}:F>"
