"""
Administrative report.

Operational statistics for deployments.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..reports.models import Report


@dataclass(slots=True)
class AdministrativeReport(Report):

    duration_seconds: float = 0.0

    completed: bool = False

    question_count: int = 0

    completed_goals: int = 0

    total_goals: int = 0