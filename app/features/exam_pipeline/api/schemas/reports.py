"""Report API schemas matching the reporting domain model."""
from __future__ import annotations
from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field

class RecommendationResponse(BaseModel):
    priority: str
    category: str
    title: str
    description: str
    action: str

class GoalMetricResponse(BaseModel):
    goal_id: str
    title: str
    score: float
    coverage: float
    completed: bool
    mastery: float = 0.0
    confidence: float = 0.0
    time_budget_seconds: float = 0.0
    time_elapsed_seconds: float = 0.0
    time_remaining_seconds: float = 0.0
    time_outcome: str | None = None

class IndicatorMetricResponse(BaseModel):
    indicator_id: str
    description: str
    achieved_level: float
    confidence: float
    attempts: int
    demonstrated: bool
    achievement_level: float = 0.0
    mastery: float = 0.0
    evidence_strength: float = 0.0
    bloom_level: str = ""
    required: bool = False
    feedback: str | None = None

class MetricsResponse(BaseModel):
    overall_score: float
    overall_coverage: float
    overall_confidence: float = 0.0
    completed: bool
    total_questions: int = 0
    goal_metrics: list[GoalMetricResponse] = Field(default_factory=list)
    indicator_metrics: list[IndicatorMetricResponse] = Field(default_factory=list)

class ReportResponse(BaseModel):
    session_id: str
    student_id: str
    generated_at: datetime
    metrics: MetricsResponse
    recommendations: list[RecommendationResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
