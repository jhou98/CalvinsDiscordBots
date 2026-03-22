"""
Data models shared across the change order cogs.
"""
 
from dataclasses import dataclass, field
 
@dataclass
class DraftChangeOrder:
    """
    Represents an in-progress change order draft for a single user.
    """
    date: str
    submitted_at: str
    scope: str
    materials: list[tuple[str, str]] = field(default_factory=list)