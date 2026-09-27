from __future__ import annotations
from pydantic import Field
from .common import APIModel

class RubricLevelRequest(APIModel):
    level: int = Field(..., ge=1)
    label: str
    description: str
class RubricRequest(APIModel):
    id: str | None = None
    name: str = "ABET Performance Rubric"
    passing_level: int = Field(default=4, ge=1)
    levels: list[RubricLevelRequest] = Field(default_factory=list)
class CriterionRequest(APIModel):
    id: str
    code: str
    description: str
    indicator_id: str
    goal_id: str | None = None
    learning_outcome_id: str | None = None
    outcome_id: str | None = None
    observable: str = ""
    weight: float = Field(default=1.0, ge=0)
    minimum_level: int = Field(default=4, ge=1)
    rubric_id: str | None = None
class LearningOutcomeRequest(APIModel):
    id: str
    code: str
    title: str
    description: str
    outcome_id: str
    goal_ids: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0)
    passing_threshold: float = Field(default=.70, ge=0, le=1)
class OutcomeRequest(APIModel):
    id: str
    code: str
    title: str
    description: str
    learning_outcome_ids: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0)
    passing_threshold: float = Field(default=.70, ge=0, le=1)
class AssessmentPlanRequest(APIModel):
    id: str | None = None
    name: str = "ABET Assessment Plan"
    goal_model_id: str | None = None
    outcomes: list[OutcomeRequest] = Field(default_factory=list)
    learning_outcomes: list[LearningOutcomeRequest] = Field(default_factory=list)
    criteria: list[CriterionRequest] = Field(default_factory=list)
    rubrics: list[RubricRequest] = Field(default_factory=list)
    required_coverage: float = Field(default=1.0, ge=0, le=1)
    minimum_attainment: float = Field(default=.70, ge=0, le=1)
