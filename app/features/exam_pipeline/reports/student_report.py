"""
Student report.

Focused on feedback rather than assessment internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..reports.models import Report


@dataclass(slots=True)
class StudentReport(Report):

    strengths: list[str] = field(
        default_factory=list
    )

    weaknesses: list[str] = field(
        default_factory=list
    )

    next_steps: list[str] = field(
        default_factory=list
    )

    encouragement: str = ""