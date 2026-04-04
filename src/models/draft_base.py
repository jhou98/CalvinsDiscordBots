"""
Base dataclass shared by all draft models.
Provides created_at for TTL expiry and message for sweep eviction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import discord


@dataclass
class DraftBase:
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: discord.Message | None = field(default=None, repr=False)
