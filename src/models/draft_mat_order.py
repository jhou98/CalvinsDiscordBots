"""
Data model for /matorder drafts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.draft_base import DraftBase


@dataclass
class DraftMatOrder(DraftBase):
    date_requested: str = ""
    requested_by: str = ""
    required_date: str = ""
    site_contact: str = ""
    delivery_notes: str = ""
    submitted_at: str = ""
    materials: list[tuple[str, str]] = field(default_factory=list)
