"""
Data model for /inspectionreq drafts.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.draft_base import DraftBase


@dataclass
class DraftInspection(DraftBase):
    date_requested: str = ""
    inspection_date: str = ""
    inspection_type: str = ""
    site_contact: str = ""
    am_pm: str = ""
    submitted_at: str = ""