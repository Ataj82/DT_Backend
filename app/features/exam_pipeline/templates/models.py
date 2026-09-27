"""
templates/models.py

Interview template domain models.

A template defines HOW an assessment interview should be conducted.
It is generated after professor validation and before an interview
session begins.

The template is immutable and reusable across multiple interview
sessions.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Enumerations
# ============================================================

class ProbePolicy(str, Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"
    SCAFFOLD = "scaffold"
    SIMPLIFY = "simplify"
    VERIFY = "verify"


class StoppingPolicy(str, Enum):
    ALL_GOALS = "all_goals"
    COVERAGE = "coverage"
    CONFIDENCE = "confidence"
    TIME_LIMIT = "time_limit"
    HYBRID = "hybrid"


class GoalOrdering(str, Enum):
    SEQUENTIAL = "sequential"
    DIFFICULTY = "difficulty"
    IMPORTANCE = "importance"
    ADAPTIVE = "adaptive"


# ============================================================
# Timing
# ============================================================

class TimeConfiguration(BaseModel):

    interview_minutes: int = 30

    per_goal_minutes: Optional[int] = None

    warning_minutes_remaining: int = 5


# ============================================================
# Interview Template
# ============================================================

class InterviewTemplate(BaseModel):
    """
    Defines how an interview should be executed.

    It contains only interview strategy.

    Runtime state belongs to InterviewSession.
    """

    id: str

    name: str

    description: Optional[str] = None

    goal_model_id: str

    goal_ordering: GoalOrdering = GoalOrdering.SEQUENTIAL

    probe_policy: ProbePolicy = ProbePolicy.ADAPTIVE

    stopping_policy: StoppingPolicy = StoppingPolicy.HYBRID

    coverage_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
    )

    confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )

    maximum_questions: int = 30

    timing: TimeConfiguration = Field(
        default_factory=TimeConfiguration
    )

    metadata: Dict[str, str] = Field(default_factory=dict)