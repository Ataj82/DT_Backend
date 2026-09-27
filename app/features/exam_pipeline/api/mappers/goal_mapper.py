"""
app/api/mappers/goal_mapper.py

Maps Goal domain models to API response schemas.
"""

from __future__ import annotations

from ...api.schemas.common import BloomLevel as APIBloomLevel
from ...api.schemas.goals import (
    IndicatorResponse,
    GoalResponse,
    GoalSummary,
    GoalListResponse,
    GenerateGoalsResponse,
    ReviewGoalsResponse,
)


class GoalMapper:
    """
    Converts Goal domain models into API DTOs.
    """

    # ==========================================================
    # Bloom Level
    # ==========================================================

    @staticmethod
    def _map_bloom_level(level):
        return APIBloomLevel(level.value)

    # ==========================================================
    # Indicator
    # ==========================================================

    @classmethod
    def to_indicator(cls, indicator) -> IndicatorResponse:
        return IndicatorResponse(
            id=indicator.id,
            name=indicator.name,
            indicator_type=indicator.indicator_type,
            description=indicator.description,
            required=indicator.required,
            weight=indicator.weight,
            difficulty=getattr(indicator, "difficulty", None),
        )

    # ==========================================================
    # Goal
    # ==========================================================

    @classmethod
    def to_goal(cls, goal) -> GoalResponse:
        return GoalResponse(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            bloom_level=cls._map_bloom_level(goal.bloom_level),
            goal_type=getattr(goal, "goal_type", "theoretical"),
            importance=goal.importance,
            difficulty=goal.difficulty,
            estimated_questions=goal.estimated_questions,
            allocated_minutes=getattr(goal, "allocated_minutes", None),
            allocated_seconds=getattr(goal, "allocated_seconds", None),
            weight=getattr(goal, "weight", 1.0),
            related_concept_ids=list(goal.related_concept_ids),
            prerequisite_goal_ids=list(goal.prerequisite_goal_ids),
            indicators=[
                cls.to_indicator(indicator)
                for indicator in goal.indicators
            ],
            status=goal.status,
        )

    # ==========================================================
    # Goal Summary
    # ==========================================================

    @classmethod
    def to_summary(cls, goal) -> GoalSummary:
        return GoalSummary(
            id=goal.id,
            title=goal.title,
            bloom_level=cls._map_bloom_level(goal.bloom_level),
            status=goal.status,
            indicator_count=len(goal.indicators),
        )

    # ==========================================================
    # Goal List
    # ==========================================================

    @classmethod
    def to_goal_list(cls, goal_model) -> GoalListResponse:
        return GoalListResponse(
            goal_model_id=goal_model.id,
            knowledge_base_id=goal_model.knowledge_base_id,
            goal_count=len(goal_model.goals),
            goals=[
                cls.to_summary(goal)
                for goal in goal_model.goals
            ],
        )

    # ==========================================================
    # Generate Response
    # ==========================================================

    @classmethod
    def to_generate_response(
        cls,
        goal_model,
    ) -> GenerateGoalsResponse:

        return GenerateGoalsResponse(
            goal_model_id=goal_model.id,
            knowledge_base_id=goal_model.knowledge_base_id,
            generated_by=goal_model.generated_by,
            version=goal_model.version,
            goal_count=len(goal_model.goals),
            goals=[
                cls.to_goal(goal)
                for goal in goal_model.goals
            ],
        )

    # ==========================================================
    # Review Response
    # ==========================================================

    @classmethod
    def to_review_response(
        cls,
        goal_model,
        rejected_goal_ids: list[str],
    ) -> ReviewGoalsResponse:

        approved_goal_ids = [
            goal.id
            for goal in goal_model.goals
            if goal.status.name == "APPROVED"
        ]

        return ReviewGoalsResponse(
            goal_model_id=goal_model.id,
            approved_goal_ids=approved_goal_ids,
            rejected_goal_ids=rejected_goal_ids,
        )

    # ==========================================================
    # Utilities
    # ==========================================================

    @classmethod
    def to_goal_responses(cls, goals):
        return [
            cls.to_goal(goal)
            for goal in goals
        ]