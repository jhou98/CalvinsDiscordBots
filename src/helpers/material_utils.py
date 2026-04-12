"""
Material parsing, formatting, and validation utilities.
"""

from src.helpers.validation_utils import is_numeric


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


def validate_materials(raw: str) -> tuple[list[tuple[str, str]], str | None]:
    """
    Parse and validate a raw materials string.
    Returns (valid_materials, error_message_or_none).
    On success error_message is None. On failure the list is empty.
    """
    material_list, parse_errors = parse_materials(raw)
    non_numeric = [f"`{name} - {qty}`" for name, qty in material_list if not is_numeric(qty)]

    if not parse_errors and not non_numeric:
        return material_list, None

    error_lines: list[str] = []
    if parse_errors:
        error_lines.append(
            "**Missing quantity** (expected `Name - Quantity`):\n"
            + "\n".join(f"• `{e}`" for e in parse_errors)
        )
    if non_numeric:
        error_lines.append(
            "**Non-numeric quantity:**\n" + "\n".join(f"• {e}" for e in non_numeric)
        )
    error_msg = (
        "⚠️ Some lines couldn't be added:\n\n"
        + "\n\n".join(error_lines)
        + "\n\nUse the format `Name - Quantity` with a numeric quantity."
    )
    return [], error_msg
