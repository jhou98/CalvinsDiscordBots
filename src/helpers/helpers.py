"""
Shared helpers used by both change order cogs.

Eventually might want to separate these out into separate files / classes
But for now for simplicity will keep them as a single utils folder
"""

import discord
from datetime import datetime, timezone

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
    except ValueError:
        raise ValueError(f"Invalid date format `{raw.strip()}` — expected MM/DD/YYYY (e.g. `03/15/2026`).")
    
    return raw.strip()

def discord_timestamp() -> str:
    """Return a Discord-formatted timestamp that renders in each user's local timezone."""
    unix_now = int(datetime.now(timezone.utc).timestamp())
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
# Embed builder
# ---------------------------------------------------------------------------

def build_change_order_embed(
    user: discord.User | discord.Member,
    date: str,
    submitted_at: str,
    scope: str,
    material_list: list[tuple[str, str]],
    *,
    title: str = "📋 Change Order",
    color: discord.Color = discord.Color.yellow(),
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