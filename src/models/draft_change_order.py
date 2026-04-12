"""
Data model for /changeorder drafts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.draft_base import DraftBase


@dataclass
class DraftChangeOrder(DraftBase):
    date_requested: str = ""
    submitted_at: str = ""
    scope: str = ""
    materials: list[tuple[str, str]] = field(default_factory=list)
