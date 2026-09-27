"""
app/api/schemas/goals.py

API schemas for assessment goal generation, authoring, and review.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import ConfigDict, Field

from ...api.schemas.common import (
    APIModel,
    BloomLevel,
)
from ...goals.models import (
    GoalStatus,
    GoalType,
    IndicatorType,
)


# ==========================================================
# Goal Indicator
# ==========================================================

class IndicatorResponse(APIModel):
    """
    Observable evidence required to satisfy a goal.
    """

    id: str

    name: str

    indicator_type: IndicatorType = IndicatorType.CONCEPT

    description: Optional[str] = None

    required: bool = True

    weight: float = 1.0

    difficulty: float | None = Field(default=None, ge=0.0, le=1.0)


class GoalIndicatorCreateInput(APIModel):
    """
    Payload for creating or updating an indicator.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )

    name: str = Field(min_length=1, max_length=255)

    indicator_type: IndicatorType = IndicatorType.CONCEPT

    description: Optional[str] = None

    required: bool = True

    weight: float = Field(default=1.0, ge=0.0)

    difficulty: Optional[Union[float, str]] = None


# ==========================================================
# Goal
# ==========================================================

class GoalResponse(APIModel):
    """
    One assessment goal.
    """

    id: str

    title: str

    description: Optional[str] = None

    bloom_level: BloomLevel

    goal_type: GoalType = GoalType.THEORETICAL

    importance: float = 1.0

    difficulty: float = 0.5

    estimated_questions: int = 3

    allocated_minutes: Optional[int] = None

    allocated_seconds: Optional[int] = None

    weight: float = 1.0

    related_concept_ids: list[str] = Field(
        default_factory=list
    )

    prerequisite_goal_ids: list[str] = Field(
        default_factory=list
    )

    indicators: list[IndicatorResponse] = Field(
        default_factory=list
    )

    status: GoalStatus = GoalStatus.GENERATED


class GoalCreateInput(APIModel):
    """
    Structured payload for authoring a goal.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )

    title: str = Field(min_length=1, max_length=300)

    description: Optional[str] = None

    bloom_level: BloomLevel = BloomLevel.UNDERSTAND

    goal_type: GoalType = GoalType.THEORETICAL

    importance: float = Field(default=1.0, ge=0.0)

    difficulty: Union[float, str] = Field(default=0.5)

    weight: float = Field(default=1.0, ge=0.0)

    estimated_questions: int = Field(default=3, ge=1, le=50)

    allocated_minutes: Optional[int] = Field(default=None, ge=1)

    allocated_seconds: Optional[int] = Field(default=None, ge=1)

    indicators: list[Union[str, GoalIndicatorCreateInput]] = Field(default_factory=list)


# ==========================================================
# Goal Model Authoring & Creation
# ==========================================================

class GoalModelCreateRequest(APIModel):
    """
    Directly creates and persists a GoalModel from goals (either strings or objects).
    """

    title: Optional[str] = None

    knowledge_base_id: str = "default_kb"

    course_id: Optional[str] = None

    lesson_id: Optional[str] = None

    duration_minutes: Optional[int] = Field(default=None, ge=1)

    goals: list[Union[str, GoalCreateInput]] = Field(min_length=1)


# ==========================================================
# Generate
# ==========================================================

class GenerateGoalsRequest(APIModel):
    """
    Generate assessment goals from a knowledge base graph.
    """

    knowledge_id: str

    max_goals: int = Field(
        default=10,
        ge=1,
    )

    include_optional: bool = True


class GenerateGoalsResponse(APIModel):
    """
    Generated GoalModel.
    """

    goal_model_id: str

    knowledge_base_id: str

    generated_by: str

    version: str

    goal_count: int

    goals: list[GoalResponse]


# ==========================================================
# Review
# ==========================================================

class GoalReview(APIModel):
    """
    Professor review of one goal.
    """

    goal_id: str

    approved: bool = True


class ReviewGoalsRequest(APIModel):
    """
    Review a generated GoalModel.
    """

    goal_model_id: str

    reviews: list[GoalReview]


class ReviewGoalsResponse(APIModel):
    """
    Result after review.
    """

    goal_model_id: str

    approved_goal_ids: list[str]

    rejected_goal_ids: list[str]


# ==========================================================
# Goal Summary
# ==========================================================

class GoalSummary(APIModel):
    """
    Lightweight goal information.
    """

    id: str

    title: str

    bloom_level: BloomLevel

    status: GoalStatus

    indicator_count: int


class GoalListResponse(APIModel):
    """
    Summary of a GoalModel.
    """

    goal_model_id: str

    knowledge_base_id: str

    title: Optional[str] = None

    course_id: Optional[str] = None

    lesson_id: Optional[str] = None

    goal_count: int

    goals: list[GoalSummary]