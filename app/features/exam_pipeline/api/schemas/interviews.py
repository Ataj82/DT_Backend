"""
app/api/schemas/interviews.py

API schemas for interview management.

This module is the single source of truth for Interview API
requests and responses.

Design principles
-----------------
- One request model
- One session model
- One conversation model
- One assessment model
- No duplicated DTOs
- Stable public API
- Transport assessment values already produced by the backend
- Never calculate assessment metrics inside API schemas

Assessment ownership
--------------------
The assessment/application/domain backend is responsible for:

- achievement level
- confidence
- evidence strength
- demonstrated state
- completion state
- attempts
- mastery
- final assessment result

These Pydantic models only validate and transport those values.

Metric semantics
----------------
- achievement_level: ordinal assessment level, 1..6
- confidence: normalized probability/confidence, 0..1
- evidence_strength: normalized evidence strength, 0..1
- mastery: normalized goal mastery, 0..1
- score: public/API score when explicitly produced by the backend
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ...api.schemas.common import (
    APIModel,
    InterviewStatus,
    NavigationType,
    ReportType,
    StrategyType,
)


# ==========================================================
# Interview Configuration
# ==========================================================


class InterviewConfigurationRequest(APIModel):
    """
    Interview configuration supplied during session creation.

    Configuration values are validated here, but no assessment
    decisions are made by this schema.
    """

    strategy: StrategyType = StrategyType.GOAL_BASED

    navigation: NavigationType = NavigationType.ADAPTIVE

    report: ReportType = ReportType.RESEARCH

    # Optional teacher-selected interview language. When omitted, the
    # interview resolves language from the selected knowledge base.
    language: str | None = Field(
        default=None,
        pattern=r"^(en|fa)$",
        description="Optional interview language override: en or fa.",
    )

    # Deprecated compatibility field. It is accepted so older clients do
    # not receive HTTP 422, but it is ignored by adaptive navigation.
    max_questions_per_indicator: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description=(
            "Deprecated compatibility field. Ignored; interview duration "
            "is the authoritative stopping constraint."
        ),
    )

    # Authoritative time-forced interview budget.
    duration_seconds: int = Field(
        default=600,
        ge=30,
        le=86400,
        description=(
            "Total wall-clock interview duration. When the deadline is "
            "reached, the current answered turn is completed and no new "
            "question is generated."
        ),
    )

    # Optional explicit per-goal time budgets. When supplied, every approved
    # goal must appear exactly once and the budgets must sum to the global
    # interview duration. When omitted, the backend derives deterministic
    # goal-specific budgets from goal importance/difficulty/question load.
    goal_time_allocations_seconds: dict[str, int] | None = Field(
        default=None,
        description=(
            "Optional explicit goal_id -> seconds allocation. Provide all "
            "approved goal IDs; values must be positive and sum exactly to "
            "duration_seconds."
        ),
    )

    passing_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
    )

    allow_followup_questions: bool = True

    gap_minutes: int | None = Field(default=5)

    materials: list[Any] | None = Field(default_factory=list)

    student_slots: dict[str, Any] | None = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    model_config = {"extra": "ignore"}


# ==========================================================
# Create Interview
# ==========================================================


class CreateInterviewRequest(APIModel):
    """
    Request for creating an interview session.

    Only identifiers are transported through the API.
    Domain models are loaded by the InterviewService.
    """

    student_id: str

    knowledge_id: str

    goal_model_id: str

    configuration: InterviewConfigurationRequest


# ==========================================================
# Conversation
# ==========================================================


class SubmitAnswerRequest(APIModel):
    """
    Learner answer submitted for the current interview question.
    """

    answer: str = Field(
        ...,
        min_length=1,
    )

    turn_index: int | None = Field(
        default=None,
        ge=1,
        description=(
            "One-based index of the interviewer turn being answered. "
            "When supplied, the server rejects stale/out-of-order submissions."
        ),
    )

    elapsed_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional client-reported response duration in seconds.",
    )


class ConversationTurnResponse(APIModel):
    """
    One question/answer exchange.

    Assessment fields are optional because a turn may exist
    before assessment evaluation has been completed.

    These fields are transported from canonical assessment
    state. No assessment calculation occurs here.
    """

    turn_number: int

    question: str

    answer: str | None = None

    feedback: str | None = None

    timestamp: datetime | None = None

    goal_id: str | None = None

    indicator_id: str | None = None

    score: float | None = None

    achievement_level: float | None = Field(
        default=None,
        ge=1.0,
        le=6.0,
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    evidence_strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    # Evaluation details captured for this exact answer.
    # These are transported from backend evaluation state; the API
    # layer never calculates them.
    bloom_level: str | None = None

    missing_elements: list[str] = Field(
        default_factory=list,
    )

    rationale: str | None = None

    coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    demonstrated: bool | None = None

    attempts: int | None = Field(
        default=None,
        ge=0,
    )

    # Adaptive difficulty snapshot for this exact turn.
    difficulty_before: float | None = Field(default=None, ge=0.0, le=1.0)
    difficulty_after: float | None = Field(default=None, ge=0.0, le=1.0)
    difficulty_performance: float | None = Field(default=None, ge=0.0, le=1.0)
    difficulty_direction: str | None = None

    status: str | None = None


# ==========================================================
# Progress
# ==========================================================


class IndicatorProgressResponse(APIModel):
    """
    Assessment state of one indicator.

    All assessment values are produced by the assessment backend.

    This schema performs validation only. It does not calculate
    achievement, confidence, evidence strength, mastery, or
    completion.
    """

    # ------------------------------------------------------
    # Indicator identity
    # ------------------------------------------------------

    id: str

    description: str

    bloom_level: str

    # ------------------------------------------------------
    # Assessment state
    # ------------------------------------------------------

    attempts: int = Field(
        default=0,
        ge=0,
    )

    demonstrated: bool = False

    achievement_level: float | None = Field(
        default=None,
        ge=1.0,
        le=6.0,
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    evidence_strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    feedback: str = ""


class GoalProgressResponse(APIModel):
    """
    Assessment progress for one goal.

    Mastery and confidence are supplied by the assessment backend.

    None means that authoritative goal-level aggregation has not
    yet been produced.
    """

    goal_id: str

    goal_name: str

    completed: bool = False

    coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    time_budget_seconds: float = Field(default=0.0, ge=0.0)
    time_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    time_remaining_seconds: float = Field(default=0.0, ge=0.0)
    time_outcome: str | None = None

    assessed_indicators: int = Field(default=0, ge=0)
    total_indicators: int = Field(default=0, ge=0)

    indicators: list[IndicatorProgressResponse] = Field(
        default_factory=list,
    )


# ==========================================================
# Assessment
# ==========================================================


class AssessmentResultResponse(APIModel):
    """
    Final assessment result.

    The values are produced by the application's result-building
    layer.

    This schema only validates and transports the result.
    """

    overall_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )

    passed: bool

    summary: str

    recommendations: list[str] = Field(
        default_factory=list,
    )


# ==========================================================
# Session
# ==========================================================


class InterviewSessionResponse(APIModel):
    """
    Complete interview session returned to the client.
    """

    session_id: str

    student_id: str

    knowledge_id: str

    goal_model_id: str

    status: InterviewStatus

    created_at: datetime | None = None

    current_question: str | None = None

    current_goal: str | None = None

    duration_seconds: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    remaining_seconds: float | None = Field(default=None, ge=0)
    current_goal_id: str | None = None
    current_goal_budget_seconds: float | None = Field(default=None, ge=0)
    current_goal_elapsed_seconds: float | None = Field(default=None, ge=0)
    current_goal_remaining_seconds: float | None = Field(default=None, ge=0)
    goal_time_snapshot: dict[str, Any] | None = None

    # Live assessment metrics. These are read from the canonical
    # CoverageEngine/GoalState assessment state; the API schema never calculates them.
    overall_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    completed_goals: int = Field(default=0, ge=0)
    total_goals: int = Field(default=0, ge=0)
    questions_asked: int = Field(default=0, ge=0)
    assessed_indicators: int = Field(default=0, ge=0)
    total_indicators: int = Field(default=0, ge=0)
    current_indicator_id: str | None = None
    current_bloom_level: str | None = None
    current_difficulty: float | None = Field(default=None, ge=0.0, le=1.0)

    progress: list[GoalProgressResponse] = Field(
        default_factory=list,
    )

    conversation: list[ConversationTurnResponse] = Field(
        default_factory=list,
    )

    result: AssessmentResultResponse | None = None

    configuration: InterviewConfigurationRequest | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


# ==========================================================
# Lightweight State
# ==========================================================


class InterviewStateResponse(APIModel):
    """
    Lightweight interview state used for polling endpoints.

    Progress is represented as a normalized 0..1 value.
    """

    session_id: str

    status: InterviewStatus

    current_goal: str | None = None

    current_indicator: str | None = None

    completed_goals: int = Field(
        ...,
        ge=0,
    )

    total_goals: int = Field(
        ...,
        ge=0,
    )

    questions_asked: int = Field(
        ...,
        ge=0,
    )

    progress: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )


# ==========================================================
# Start Interview
# ==========================================================


class StartInterviewResponse(APIModel):
    """Response returned when an interview starts successfully."""

    session_id: str
    status: InterviewStatus
    first_question: str
    turn_index: int = Field(default=1, ge=1)
    duration_seconds: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    remaining_seconds: float | None = Field(default=None, ge=0)
    current_goal_id: str | None = None
    current_goal_budget_seconds: float | None = Field(default=None, ge=0)
    current_goal_elapsed_seconds: float | None = Field(default=None, ge=0)
    current_goal_remaining_seconds: float | None = Field(default=None, ge=0)
    goal_time_snapshot: dict[str, Any] | None = None
    overall_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    completed_goals: int = Field(default=0, ge=0)
    total_goals: int = Field(default=0, ge=0)
    questions_asked: int = Field(default=0, ge=0)
    assessed_indicators: int = Field(default=0, ge=0)
    total_indicators: int = Field(default=0, ge=0)
    current_indicator_id: str | None = None
    current_bloom_level: str | None = None
    current_difficulty: float | None = Field(default=None, ge=0.0, le=1.0)


# ==========================================================
# Question
# ==========================================================


class QuestionResponse(APIModel):
    """
    Current interview question and its assessment context.
    """

    session_id: str

    turn_index: int = Field(..., ge=1)

    question: str

    goal_id: str

    indicator_id: str

    bloom_level: str

    attempt: int = Field(
        ...,
        ge=1,
    )

    is_followup: bool

    difficulty: float | None = Field(default=None, ge=0.0, le=1.0)
    difficulty_reason: str | None = None


# ==========================================================
# Answer Evaluation
# ==========================================================


class AnswerEvaluation(APIModel):
    """
    Complete evaluation and assessment snapshot for the answer that
    was just submitted.

    Values are transported from the backend; this schema never calculates
    assessment metrics.
    """

    # Exact identity of the answered turn.
    turn_index: int = Field(
        ...,
        ge=1,
        description="One-based index of the evaluated interviewer turn.",
    )
    question: str
    answer: str

    # Answer-level evaluation
    score: float | None = None

    achievement_level: float | None = Field(
        default=1.0,
        ge=1.0,
        le=6.0,
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )

    evidence_strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )

    indicator_demonstrated: bool
    demonstrated: bool | None = None
    bloom_level: str | None = None
    missing_elements: list[str] = Field(default_factory=list)
    feedback: str = ""
    rationale: str | None = None

    # Assessment-state snapshot after applying this answer
    covered: bool = False
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    mastery: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts: int | None = Field(default=None, ge=0)
    status: str | None = None
    goal_id: str | None = None
    indicator_id: str | None = None
    assessment_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SubmitAnswerResponse(APIModel):
    """
    Result of submitting one learner answer.

    Lifecycle status is deliberately separate from the assessment
    decision status inside ``evaluation``. A goal can be marked
    failed/exhausted while the interview remains RUNNING because
    another goal is still assessable.
    """

    evaluation: AnswerEvaluation

    next_question: QuestionResponse | None = None

    # Session lifecycle, never the goal/evaluation decision status.
    status: InterviewStatus = InterviewStatus.RUNNING

    interview_completed: bool = False

    duration_seconds: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    remaining_seconds: float | None = Field(default=None, ge=0)
    current_goal_id: str | None = None
    current_goal_budget_seconds: float | None = Field(default=None, ge=0)
    current_goal_elapsed_seconds: float | None = Field(default=None, ge=0)
    current_goal_remaining_seconds: float | None = Field(default=None, ge=0)
    goal_time_snapshot: dict[str, Any] | None = None
    overall_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    completed_goals: int = Field(default=0, ge=0)
    total_goals: int = Field(default=0, ge=0)
    questions_asked: int = Field(default=0, ge=0)
    assessed_indicators: int = Field(default=0, ge=0)
    total_indicators: int = Field(default=0, ge=0)
    current_indicator_id: str | None = None
    current_bloom_level: str | None = None
    current_difficulty: float | None = Field(default=None, ge=0.0, le=1.0)
    progress: list[GoalProgressResponse] = Field(default_factory=list)


# ==========================================================
# Finish Interview
# ==========================================================


class FinishInterviewResponse(APIModel):
    """
    Response returned when an interview is explicitly or
    automatically finished.
    """

    session_id: str

    status: InterviewStatus

    completed_at: datetime