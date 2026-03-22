"""
Shared helpers used by both change order cogs.

Eventually might want to separate these out into separate files / classes
But for now for simplicity will keep them as a single utils folder
"""

from datetime import UTC, datetime

import discord


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------


def parse_materials(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Parse a freeform material string (one item per line, format: Name - Quantity).
    Returns (material_list, parse_errors).
      material_list  — list of (name, qty) tuples for valid lines
      parse_errors   — list of raw lines that couldn't be parsed
    """
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    material_list = []
    parse_errors = []

    for line in lines:
        if " - " in line:
            name, qty = line.split(" - ", 1)
            material_list.append((name.strip(), qty.strip()))
        else:
            parse_errors.append(line)

    return material_list, parse_errors


def format_materials(material_list: list[tuple[str, str]]) -> str:
    """Format a list of (name, qty) tuples into a Discord embed string."""
    if not material_list:
        return "_No materials listed._"
    return "\n".join(f"`{name}` — **{qty}**" for name, qty in material_list)


# ---------------------------------------------------------------------------
# Plain text builder
# ---------------------------------------------------------------------------


def format_plain_text(
    user: discord.User | discord.Member,
    date: str,
    scope: str,
    material_list: list[tuple[str, str]],
) -> str:
    """
    Return a plain-text representation of a change order for easy copy-pasting.
    Materials use Name - Quantity format, matching the original input convention.
    """
    lines = [
        "CHANGE ORDER",
        f"Date Requested: {date}",
        f"Submitted By:   {user.display_name}",
        "",
        "Scope Added:",
        scope,
        "",
        "Materials:",
    ]
    if material_list:
        lines += [f"  {name} - {qty}" for name, qty in material_list]
    else:
        lines.append("  No materials listed.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Embed builder
# ---------------------------------------------------------------------------
_DEFAULT_EMBED_COLOR = discord.Color.yellow()


def build_change_order_embed(
    user: discord.User | discord.Member,
    date: str,
    submitted_at: str,
    scope: str,
    material_list: list[tuple[str, str]],
    *,
    title: str = "📋 Change Order",
    color: discord.Color = _DEFAULT_EMBED_COLOR,
) -> discord.Embed:
    """
    Build a formatted change order embed.
    Used by both the single-modal and multi-step flows.
    Pass a custom title/color to distinguish drafts from final submissions.
    """
    embed = discord.Embed(title=title, color=color)

    embed.add_field(name="📅 Date Requested", value=date, inline=True)
    embed.add_field(name="🕐 Submitted At", value=submitted_at, inline=True)
    embed.add_field(name="👤 Submitted By", value=user.mention, inline=True)
    embed.add_field(name="🔧 Scope Added", value=scope, inline=False)
    embed.add_field(
        name=f"📦 Materials ({len(material_list)} item{'s' if len(material_list) != 1 else ''})",
        value=format_materials(material_list),
        inline=False,
    )
    embed.set_footer(text="Change Order System")

    return embed
