"""
Instructor report.

Designed for educators.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..reports.models import (
    Report,
    GoalSummary,
)


@dataclass(slots=True)
class InstructorReport(Report):

    coverage: float = 0.0

    mastery: float = 0.0

    confidence: float = 0.0

    goals: list[GoalSummary] = field(
        default_factory=list
    )

    strengths: list[str] = field(
        default_factory=list
    )

    weaknesses: list[str] = field(
        default_factory=list
    )

    recommendations: list[str] = field(
        default_factory=list
    )