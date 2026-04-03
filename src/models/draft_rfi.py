"""
Data model for /rfi drafts.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.draft_base import DraftBase


@dataclass
class DraftRfi(DraftBase):
    date_requested: str = ""
    requested_by: str = ""
    questions: str = ""
    issues: str = ""
    proposed_solution: str = ""
    impact: str = ""
    required_by: str = ""
    submitted_at: str = ""