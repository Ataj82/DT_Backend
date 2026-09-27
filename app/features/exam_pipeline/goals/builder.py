"""
goals/builder.py

Helper service and factory for constructing and authoring GoalModels.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from .models import Goal, GoalIndicator, GoalModel, GoalStatus, GoalType, IndicatorType
from ..knowledge.models import BloomLevel


class GoalBuilder:
    """
    Fluid and batch builder for assessment goals and goal models.
    """

    @staticmethod
    def build_from_input(
        *,
        knowledge_base_id: str = "default_kb",
        goals_data: list[Union[str, dict[str, Any]]],
        title: Optional[str] = None,
        course_id: Optional[str] = None,
        lesson_id: Optional[str] = None,
        duration_minutes: Optional[int] = None,
    ) -> GoalModel:
        """
        Builds a verified GoalModel from string titles or structured dictionaries.
        """
        return GoalModel.create_from_input(
            knowledge_base_id=knowledge_base_id,
            goals_data=goals_data,
            title=title,
            course_id=course_id,
            lesson_id=lesson_id,
            total_duration_minutes=duration_minutes,
        )

    @staticmethod
    def create_single_goal(
        *,
        title: str,
        description: Optional[str] = None,
        bloom_level: str | BloomLevel = BloomLevel.UNDERSTAND,
        goal_type: str | GoalType = GoalType.THEORETICAL,
        importance: float = 1.0,
        difficulty: float = 0.5,
        estimated_questions: int = 3,
        allocated_minutes: Optional[int] = None,
        indicators: list[GoalIndicator] | None = None,
    ) -> Goal:
        """
        Constructs a validated single Goal instance.
        """
        if isinstance(bloom_level, str):
            try:
                bloom_level = BloomLevel(bloom_level.lower())
            except ValueError:
                bloom_level = BloomLevel.UNDERSTAND

        if isinstance(goal_type, str):
            try:
                goal_type = GoalType(goal_type.lower())
            except ValueError:
                goal_type = GoalType.THEORETICAL

        inds = indicators or [
            GoalIndicator(
                name=title.strip(),
                indicator_type=IndicatorType.CONCEPT,
                description=description or f"ارزیابی {title.strip()}",
                required=True,
                weight=1.0,
                difficulty=difficulty,
            )
        ]

        return Goal(
            title=title.strip(),
            description=description,
            bloom_level=bloom_level,
            goal_type=goal_type,
            importance=importance,
            difficulty=difficulty,
            estimated_questions=estimated_questions,
            allocated_minutes=allocated_minutes,
            allocated_seconds=(allocated_minutes * 60) if allocated_minutes else None,
            indicators=inds,
            status=GoalStatus.APPROVED,
        )
