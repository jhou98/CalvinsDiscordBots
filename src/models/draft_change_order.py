"""
Data models shared across the change order cogs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import discord


@dataclass
class DraftChangeOrder:
    """
    Represents an in-progress change order draft for a single user.

    created_at  — UTC timestamp set at creation; used for TTL expiry checks
                  and background sweep eviction.
    message     — Reference to the Discord message carrying the draft embed.
                  Stored here so the hourly sweep can edit it when evicting
                  stale drafts without needing a live View object.
    """

    date: str
    submitted_at: str
    scope: str
    materials: list[tuple[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: discord.Message | None = field(default=None, repr=False)
