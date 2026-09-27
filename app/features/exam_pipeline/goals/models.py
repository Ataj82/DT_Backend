"""
goals/models.py

Domain models representing assessment goals.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from ..knowledge.models import BloomLevel


# ==========================================================
# Enumerations
# ==========================================================

class GoalStatus(str, Enum):
    GENERATED = "generated"
    APPROVED = "approved"
    MODIFIED = "modified"
    DISABLED = "disabled"
    DRAFT = "draft"
    ACTIVE = "active"


class IndicatorType(str, Enum):
    CONCEPT = "concept"
    OUTCOME = "learning_outcome"
    SKILL = "skill"
    MISCONCEPTION = "misconception"
    PROBLEM_SOLVING = "problem_solving"
    ANALYSIS = "analysis"
    CRITERION = "criterion"
    BEHAVIORAL = "behavioral"


class GoalType(str, Enum):
    THEORETICAL = "theoretical"
    PRACTICAL = "practical"
    ANALYTICAL = "analytical"
    DESIGN = "design"
    COMPREHENSIVE = "comprehensive"


# ==========================================================
# Goal Indicator
# ==========================================================

class GoalIndicator(BaseModel):
    """
    Observable evidence required to satisfy a goal.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))

    name: str

    indicator_type: IndicatorType = IndicatorType.CONCEPT

    description: Optional[str] = None

    required: bool = True

    weight: float = Field(default=1.0, ge=0)

    # Initial question difficulty for this indicator. Runtime adaptive
    # difficulty is stored in GoalState.
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0)

    rubric: Optional[dict[str, Any]] = None

    target_evidence_count: int = Field(default=1, ge=1)


# ==========================================================
# Goal
# ==========================================================

class Goal(BaseModel):
    """
    One assessment goal.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))

    title: str

    description: Optional[str] = None

    bloom_level: BloomLevel = BloomLevel.UNDERSTAND

    goal_type: GoalType = GoalType.THEORETICAL

    importance: float = Field(default=1.0, ge=0)

    difficulty: float = Field(default=0.5, ge=0, le=1)

    estimated_questions: int = Field(default=3, ge=1)

    allocated_minutes: Optional[int] = None

    allocated_seconds: Optional[int] = None

    weight: float = Field(default=1.0, ge=0)

    category: Optional[str] = None

    indicators: list[GoalIndicator] = Field(default_factory=list)

    prerequisite_goal_ids: list[str] = Field(default_factory=list)

    related_concept_ids: list[str] = Field(default_factory=list)

    status: GoalStatus = GoalStatus.GENERATED


# ==========================================================
# Goal Model
# ==========================================================

class GoalModel(BaseModel):
    """
    Complete collection of goals for an assessment or KnowledgeBase.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))

    knowledge_base_id: str

    title: Optional[str] = None

    course_id: Optional[str] = None

    lesson_id: Optional[str] = None

    goals: list[Goal] = Field(default_factory=list)

    generated_by: str = "GoalGenerator"

    version: str = "1.0"

    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def goal_count(self) -> int:
        return len(self.goals)

    def get_goal(self, goal_id: str) -> Goal | None:
        for goal in self.goals:
            if goal.id == goal_id:
                return goal
        return None

    def calculate_time_allocations(self, total_duration_seconds: int) -> dict[str, int]:
        """
        Distributes the total session duration across goals based on weight or evenly.
        Ensures sum(allocations.values()) == total_duration_seconds.
        """
        active_goals = [g for g in self.goals if g.status != GoalStatus.DISABLED]
        if not active_goals:
            return {}

        total_weight = sum(g.weight for g in active_goals) or len(active_goals)
        allocations: dict[str, int] = {}
        allocated_so_far = 0

        for i, g in enumerate(active_goals):
            if i == len(active_goals) - 1:
                # Last goal gets the remainder to avoid rounding drift
                budget = max(30, total_duration_seconds - allocated_so_far)
            else:
                ratio = g.weight / total_weight if total_weight > 0 else 1.0 / len(active_goals)
                budget = max(30, int(total_duration_seconds * ratio))
                allocated_so_far += budget
            allocations[g.id] = budget
            g.allocated_seconds = budget
            g.allocated_minutes = max(1, budget // 60)

        return allocations

    @classmethod
    def create_from_input(
        cls,
        *,
        knowledge_base_id: str,
        goals_data: list[Union[str, dict[str, Any]]],
        title: Optional[str] = None,
        course_id: Optional[str] = None,
        lesson_id: Optional[str] = None,
        total_duration_minutes: Optional[int] = None,
    ) -> "GoalModel":
        """
        Creates a complete GoalModel from a list of strings or dictionaries.
        """
        goals: list[Goal] = []
        count = len(goals_data) or 1
        per_goal_minutes = max(1, (total_duration_minutes // count) if total_duration_minutes else 5)

        for item in goals_data:
            if isinstance(item, str):
                item_title = item.strip()
                if not item_title:
                    continue
                indicator = GoalIndicator(
                    name=item_title,
                    indicator_type=IndicatorType.CONCEPT,
                    description=f"سنجش تسلط بر {item_title}",
                    required=True,
                    weight=1.0,
                    difficulty=0.5,
                )
                goal = Goal(
                    title=item_title,
                    description=f"هدف آموزشی: {item_title}",
                    bloom_level=BloomLevel.UNDERSTAND,
                    goal_type=GoalType.THEORETICAL,
                    importance=1.0,
                    difficulty=0.5,
                    estimated_questions=3,
                    allocated_minutes=per_goal_minutes,
                    allocated_seconds=per_goal_minutes * 60,
                    indicators=[indicator],
                    status=GoalStatus.APPROVED,
                )
                goals.append(goal)
            elif isinstance(item, dict):
                item_title = str(item.get("title", "")).strip() or "هدف آزمون"
                bloom_raw = str(item.get("bloom_level", "understand")).lower()
                try:
                    bloom = BloomLevel(bloom_raw)
                except ValueError:
                    bloom = BloomLevel.UNDERSTAND

                goal_type_raw = str(item.get("goal_type", "theoretical")).lower()
                try:
                    gtype = GoalType(goal_type_raw)
                except ValueError:
                    gtype = GoalType.THEORETICAL

                diff_raw = item.get("difficulty", 0.5)
                diff_map = {"easy": 0.3, "medium": 0.5, "hard": 0.8, "ساده": 0.3, "متوسط": 0.5, "سخت": 0.8}
                if isinstance(diff_raw, str):
                    diff_val = diff_map.get(diff_raw.lower(), 0.5)
                else:
                    try:
                        diff_val = float(diff_raw)
                    except (ValueError, TypeError):
                        diff_val = 0.5
                diff_val = max(0.0, min(1.0, diff_val))

                try:
                    weight_val = float(item.get("weight", 1.0))
                except (ValueError, TypeError):
                    weight_val = 1.0

                indicators_raw = item.get("indicators", [])
                indicators: list[GoalIndicator] = []
                if indicators_raw:
                    for ind in indicators_raw:
                        if isinstance(ind, dict):
                            itype_raw = str(ind.get("indicator_type", "concept")).lower()
                            try:
                                itype = IndicatorType(itype_raw)
                            except ValueError:
                                itype = IndicatorType.CONCEPT
                            ind_diff_raw = ind.get("difficulty")
                            if ind_diff_raw is not None:
                                if isinstance(ind_diff_raw, str):
                                    ind_diff = diff_map.get(ind_diff_raw.lower(), 0.5)
                                else:
                                    try:
                                        ind_diff = float(ind_diff_raw)
                                    except (ValueError, TypeError):
                                        ind_diff = 0.5
                            else:
                                ind_diff = None

                            indicators.append(GoalIndicator(
                                name=ind.get("name", item_title),
                                indicator_type=itype,
                                description=ind.get("description"),
                                required=ind.get("required", True),
                                weight=float(ind.get("weight", 1.0)),
                                difficulty=ind_diff,
                            ))
                        elif isinstance(ind, str):
                            indicators.append(GoalIndicator(name=ind.strip(), indicator_type=IndicatorType.CONCEPT))
                
                if not indicators:
                    indicators.append(GoalIndicator(
                        name=item_title,
                        indicator_type=IndicatorType.CONCEPT,
                        description=f"ارزیابی {item_title}",
                        required=True,
                        weight=1.0,
                        difficulty=diff_val,
                    ))

                goal = Goal(
                    title=item_title,
                    description=item.get("description"),
                    bloom_level=bloom,
                    goal_type=gtype,
                    importance=float(item.get("importance", 1.0)),
                    difficulty=diff_val,
                    weight=weight_val,
                    estimated_questions=int(item.get("estimated_questions", 3)),
                    allocated_minutes=int(item["allocated_minutes"]) if item.get("allocated_minutes") is not None else per_goal_minutes,
                    allocated_seconds=int(item["allocated_seconds"]) if item.get("allocated_seconds") is not None else (per_goal_minutes * 60),
                    indicators=indicators,
                    status=GoalStatus.APPROVED,
                )
                goals.append(goal)

        model = cls(
            knowledge_base_id=knowledge_base_id,
            title=title,
            course_id=course_id,
            lesson_id=lesson_id,
            goals=goals,
            generated_by="GoalBuilder",
            version="1.0",
        )

        if total_duration_minutes:
            model.calculate_time_allocations(total_duration_minutes * 60)

        return model