"""Explicit ABET assessment blueprint and runtime evidence models.

The layer is additive: existing goal/indicator assessment remains the
runtime engine. ABET adds a traceable hierarchy above it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


def _id(value: Any) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError("ID must be non-empty.")
    return value


def _prob(value: Any, name: str) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")
    return value

@dataclass(slots=True)
class RubricLevel:
    level: int
    label: str
    description: str
    def __post_init__(self):
        if not isinstance(self.level, int) or self.level < 1:
            raise ValueError("Rubric level must be a positive integer.")
        self.label = str(self.label).strip()
        self.description = str(self.description).strip()
        if not self.label or not self.description:
            raise ValueError("Rubric level label and description are required.")

@dataclass(slots=True)
class Rubric:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "ABET Performance Rubric"
    levels: list[RubricLevel] = field(default_factory=list)
    passing_level: int = 4
    def __post_init__(self):
        self.id = _id(self.id)
        self.name = str(self.name).strip()
        if not self.levels:
            self.levels = [
                RubricLevel(1, "Beginning", "Major misunderstanding or no usable evidence."),
                RubricLevel(2, "Developing", "Very limited understanding with major gaps."),
                RubricLevel(3, "Partial", "Partial understanding with significant gaps."),
                RubricLevel(4, "Adequate", "Adequate evidence of the required performance."),
                RubricLevel(5, "Strong", "Strong evidence with only minor gaps."),
                RubricLevel(6, "Comprehensive", "Comprehensive and highly convincing evidence."),
            ]
        levels = sorted(self.levels, key=lambda x: x.level)
        if [x.level for x in levels] != list(range(1, len(levels) + 1)):
            raise ValueError("Rubric levels must be contiguous starting at 1.")
        self.levels = levels
        if not 1 <= self.passing_level <= len(self.levels):
            raise ValueError("passing_level must reference an existing rubric level.")

@dataclass(slots=True)
class PerformanceCriterion:
    id: str
    code: str
    description: str
    indicator_id: str
    goal_id: str | None = None
    learning_outcome_id: str | None = None
    outcome_id: str | None = None
    observable: str = ""
    weight: float = 1.0
    minimum_level: int = 4
    rubric_id: str | None = None
    def __post_init__(self):
        self.id, self.code = _id(self.id), _id(self.code)
        self.indicator_id = _id(self.indicator_id)
        self.goal_id = _id(self.goal_id) if self.goal_id else None
        self.learning_outcome_id = _id(self.learning_outcome_id) if self.learning_outcome_id else None
        self.outcome_id = _id(self.outcome_id) if self.outcome_id else None
        self.description = str(self.description).strip()
        self.observable = str(self.observable or "").strip()
        self.weight = float(self.weight)
        if self.weight < 0: raise ValueError("Criterion weight cannot be negative.")
        if self.minimum_level < 1: raise ValueError("minimum_level must be positive.")

@dataclass(slots=True)
class LearningOutcome:
    id: str
    code: str
    title: str
    description: str
    outcome_id: str
    goal_ids: list[str] = field(default_factory=list)
    weight: float = 1.0
    passing_threshold: float = .70
    def __post_init__(self):
        self.id, self.code, self.outcome_id = _id(self.id), _id(self.code), _id(self.outcome_id)
        self.title, self.description = str(self.title).strip(), str(self.description).strip()
        self.goal_ids = [_id(x) for x in self.goal_ids]
        self.weight = float(self.weight)
        if self.weight < 0: raise ValueError("LO weight cannot be negative.")
        self.passing_threshold = _prob(self.passing_threshold, "passing_threshold")

@dataclass(slots=True)
class ABETOutcome:
    id: str
    code: str
    title: str
    description: str
    learning_outcome_ids: list[str] = field(default_factory=list)
    weight: float = 1.0
    passing_threshold: float = .70
    def __post_init__(self):
        self.id, self.code = _id(self.id), _id(self.code)
        self.title, self.description = str(self.title).strip(), str(self.description).strip()
        self.learning_outcome_ids = [_id(x) for x in self.learning_outcome_ids]
        self.weight = float(self.weight)
        if self.weight < 0: raise ValueError("Outcome weight cannot be negative.")
        self.passing_threshold = _prob(self.passing_threshold, "passing_threshold")

@dataclass(slots=True)
class AssessmentPlan:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "ABET Assessment Plan"
    outcomes: list[ABETOutcome] = field(default_factory=list)
    learning_outcomes: list[LearningOutcome] = field(default_factory=list)
    criteria: list[PerformanceCriterion] = field(default_factory=list)
    rubrics: list[Rubric] = field(default_factory=list)
    goal_model_id: str | None = None
    required_coverage: float = 1.0
    minimum_attainment: float = .70
    def __post_init__(self):
        self.id = _id(self.id)
        self.name = str(self.name).strip()
        self.required_coverage = _prob(self.required_coverage, "required_coverage")
        self.minimum_attainment = _prob(self.minimum_attainment, "minimum_attainment")
        self.goal_model_id = str(self.goal_model_id).strip() if self.goal_model_id else None
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "goal_model_id": self.goal_model_id,
            "required_coverage": self.required_coverage, "minimum_attainment": self.minimum_attainment,
            "outcomes": [o.__dict__ if hasattr(o, '__dict__') else {"id":o.id,"code":o.code,"title":o.title,"description":o.description,"learning_outcome_ids":o.learning_outcome_ids,"weight":o.weight,"passing_threshold":o.passing_threshold} for o in self.outcomes],
            "learning_outcomes": [{"id":x.id,"code":x.code,"title":x.title,"description":x.description,"outcome_id":x.outcome_id,"goal_ids":x.goal_ids,"weight":x.weight,"passing_threshold":x.passing_threshold} for x in self.learning_outcomes],
            "criteria": [{"id":x.id,"code":x.code,"description":x.description,"indicator_id":x.indicator_id,"goal_id":x.goal_id,"learning_outcome_id":x.learning_outcome_id,"outcome_id":x.outcome_id,"observable":x.observable,"weight":x.weight,"minimum_level":x.minimum_level,"rubric_id":x.rubric_id} for x in self.criteria],
            "rubrics": [{"id":r.id,"name":r.name,"passing_level":r.passing_level,"levels":[{"level":l.level,"label":l.label,"description":l.description} for l in r.levels]} for r in self.rubrics],
        }

@dataclass(slots=True)
class CriterionEvidence:
    turn_index: int
    criterion_id: str
    score: int
    confidence: float
    evidence_strength: float
    demonstrated: bool
    evidence_text: str = ""
    missing_elements: list[str] = field(default_factory=list)
    rationale: str = ""
    def __post_init__(self):
        if self.turn_index < 1: raise ValueError("turn_index must be positive.")
        self.criterion_id = _id(self.criterion_id)
        if self.score < 1: raise ValueError("criterion score must be positive.")
        self.confidence = _prob(self.confidence, "confidence")
        self.evidence_strength = _prob(self.evidence_strength, "evidence_strength")

@dataclass(slots=True)
class AssessmentTarget:
    outcome_id: str
    learning_outcome_id: str
    goal_id: str
    indicator_id: str
    criterion_id: str
    criterion_description: str
    rubric_id: str | None = None
    def to_dict(self): return {"outcome_id":self.outcome_id,"learning_outcome_id":self.learning_outcome_id,"goal_id":self.goal_id,"indicator_id":self.indicator_id,"criterion_id":self.criterion_id,"criterion_description":self.criterion_description,"rubric_id":self.rubric_id}
