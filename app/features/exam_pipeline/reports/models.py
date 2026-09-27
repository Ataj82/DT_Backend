"""
app/reports/models.py

Domain models used by the reporting subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ==========================================================
# Indicator Metric
# ==========================================================

@dataclass(slots=True)
class IndicatorMetric:

    indicator_id: str

    description: str

    # Backward-compatible reporting field. Historically this represented
    # the projected mastery/achievement value. Keep it unchanged.
    achieved_level: float

    confidence: float

    attempts: int

    demonstrated: bool

    # v12.6.3 richer reporting fields; presentation-only snapshots.
    achievement_level: float = 0.0
    mastery: float = 0.0
    evidence_strength: float = 0.0
    bloom_level: str = ""
    required: bool = False
    feedback: str | None = None


# ==========================================================
# Goal Metric
# ==========================================================

@dataclass(slots=True)
class GoalMetric:

    goal_id: str

    title: str

    score: float

    coverage: float

    completed: bool

    # Explicit reporting values so the professor/student reports do not
    # have to infer mastery from the generic score field.
    mastery: float = 0.0
    confidence: float = 0.0

    time_budget_seconds: float = 0.0
    time_elapsed_seconds: float = 0.0
    time_remaining_seconds: float = 0.0
    time_outcome: str | None = None


# ==========================================================
# Metrics
# ==========================================================

@dataclass(slots=True)
class Metrics:

    overall_score: float

    overall_coverage: float

    completed: bool

    total_questions: int

    overall_confidence: float = 0.0

    goal_metrics: list[GoalMetric] = field(default_factory=list)

    indicator_metrics: list[IndicatorMetric] = field(default_factory=list)


# ==========================================================
# Recommendation
# ==========================================================

@dataclass(slots=True)
class Recommendation:

    priority: str

    category: str

    title: str

    description: str

    action: str


# ==========================================================
# Report
# ==========================================================

@dataclass(slots=True)
class Report:

    session_id: str

    student_id: str

    generated_at: datetime = field(
        default_factory=datetime.utcnow
    )

    metrics: Metrics | None = None

    recommendations: list[Recommendation] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )