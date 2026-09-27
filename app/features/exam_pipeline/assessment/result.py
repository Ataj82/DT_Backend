"""
app/assessment/result.py

Domain models representing the final outcome of an interview
assessment.

AssessmentResult is the canonical output produced by the
assessment runtime.

Responsibilities
----------------
- Represent the final assessment result.
- Represent goal-level and indicator-level assessment results.
- Represent the interview timeline.
- Hold research/analytics metrics produced by MetricsService.
- Provide read-only convenience accessors over already-built results.

Non-responsibilities
--------------------
- Evaluating learner answers.
- Calculating indicator achievement.
- Calculating mastery.
- Calculating confidence.
- Deciding whether an indicator is demonstrated.
- Deciding whether a goal is complete.
- Selecting the next goal or indicator.
- Computing research metrics.
- Persisting results.
- Serializing results for JSON, PDF, UI, etc.

Canonical ownership
-------------------
IndicatorResult values are projected from IndicatorState by
AssessmentResultBuilder.

GoalResult values are projected from GoalState by
AssessmentResultBuilder.

ResearchMetrics values are calculated by MetricsService and are
stored here only as result data.

This module intentionally contains no dependency on the assessment
runtime, evaluator, LLM, repositories, or presentation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ==========================================================
# Indicator Result
# ==========================================================


@dataclass(slots=True)
class IndicatorResult:
    """
    Final assessment result for one indicator.

    The values in this model are snapshots of the canonical
    IndicatorState at result-building time.

    No assessment logic belongs here.
    """

    indicator_id: str

    description: str

    bloom_level: str

    required: bool

    demonstrated: bool

    mastery: float

    confidence: float

    attempts: int

    evidence_count: int

    feedback: str | None = None
    evidence_strength: float = 0.0
    missing_elements: list[str] = field(default_factory=list)
    difficulty: float | None = None


# ==========================================================
# Goal Result
# ==========================================================


@dataclass(slots=True)
class GoalResult:
    """
    Final assessment result for one goal.

    Goal-level assessment values are snapshots of the canonical
    GoalState at result-building time.

    No goal-completion or mastery logic belongs here.
    """

    goal_id: str

    title: str

    completed: bool

    coverage: float

    mastery: float

    confidence: float

    time_budget_seconds: float = 0.0
    time_elapsed_seconds: float = 0.0
    time_remaining_seconds: float = 0.0
    time_outcome: str | None = None

    indicators: list[IndicatorResult] = field(
        default_factory=list
    )


# ==========================================================
# Interview Timeline
# ==========================================================


@dataclass(slots=True)
class InterviewEvent:
    """
    Immutable-style representation of one interview event.

    The event contains contextual information only. It does not
    perform assessment reasoning.
    """

    timestamp: datetime

    event_type: str

    goal_id: str | None = None

    indicator_id: str | None = None

    details: dict[str, Any] = field(
        default_factory=dict
    )


# ==========================================================
# Research Metrics
# ==========================================================


@dataclass(slots=True)
class ResearchMetrics:
    """
    Research and interview-behaviour metrics.

    MetricsService owns the calculation of these values.

    This model only stores the resulting measurements.

    Some fields such as coverage, mastery, and confidence overlap
    conceptually with assessment-level values. They are retained
    here because they represent aggregated/reporting metrics and
    are not the canonical GoalState values.
    """

    # ------------------------------------------------------
    # Basic interview counts
    # ------------------------------------------------------

    total_questions: int = 0

    total_answers: int = 0

    completed_goals: int = 0

    total_goals: int = 0

    # ------------------------------------------------------
    # Aggregated assessment metrics
    # ------------------------------------------------------

    coverage: float = 0.0

    mastery: float = 0.0

    confidence: float = 0.0

    # ------------------------------------------------------
    # Time metrics
    # ------------------------------------------------------

    interview_duration_seconds: float = 0.0

    # ------------------------------------------------------
    # Efficiency metrics
    # ------------------------------------------------------

    average_attempts_per_indicator: float = 0.0

    average_questions_per_goal: float = 0.0

    information_gain: float = 0.0

    adaptive_transitions: int = 0

    # ------------------------------------------------------
    # Question / reasoning metrics
    # ------------------------------------------------------

    bloom_distribution: dict[str, int] = field(
        default_factory=dict
    )

    question_novelty: float = 0.0

    reasoning_depth: float = 0.0

    # ------------------------------------------------------
    # Conversation / completion metrics
    # ------------------------------------------------------

    goal_completion_rate: float = 0.0

    conversation_entropy: float = 0.0


# ==========================================================
# Assessment Result
# ==========================================================


@dataclass(slots=True)
class AssessmentResult:
    """
    Canonical final output of an interview assessment.

    AssessmentResult is a domain/result object. It contains
    already-calculated assessment state and does not calculate
    assessment decisions itself.

    Construction
    ------------
    AssessmentResultBuilder is responsible for projecting:

        InterviewSession
            ↓
        GoalState / IndicatorState
            ↓
        AssessmentResult

    MetricsService may subsequently populate ``metrics``.
    """

    # ------------------------------------------------------
    # Identity
    # ------------------------------------------------------

    session_id: str

    student_id: str

    interviewer_id: str | None = None

    # ------------------------------------------------------
    # Configuration snapshot
    # ------------------------------------------------------

    configuration: Any | None = None

    # ------------------------------------------------------
    # Lifecycle timestamps
    # ------------------------------------------------------

    started_at: datetime | None = None

    finished_at: datetime | None = None

    # ------------------------------------------------------
    # Completion state
    # ------------------------------------------------------

    completed: bool = False

    # ------------------------------------------------------
    # Assessment results
    # ------------------------------------------------------

    goals: list[GoalResult] = field(
        default_factory=list
    )

    # ------------------------------------------------------
    # Interview timeline
    # ------------------------------------------------------

    timeline: list[InterviewEvent] = field(
        default_factory=list
    )

    # ------------------------------------------------------
    # Research / analytics metrics
    # ------------------------------------------------------

    metrics: ResearchMetrics = field(
        default_factory=ResearchMetrics
    )

    # ------------------------------------------------------
    # Extensible metadata
    # ------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ======================================================
    # Convenience Properties
    # ======================================================

    @property
    def duration_seconds(self) -> float:
        """
        Return the elapsed interview duration.

        This is a pure temporal calculation over the result's
        lifecycle timestamps. It does not perform assessment
        reasoning.

        Returns
        -------
        float
            Duration in seconds.

        If either timestamp is unavailable, returns ``0.0``.
        """

        if (
            self.started_at is None
            or self.finished_at is None
        ):
            return 0.0

        return max(
            0.0,
            (
                self.finished_at - self.started_at
            ).total_seconds(),
        )

    # ------------------------------------------------------
    # Goal counts
    # ------------------------------------------------------

    @property
    def completed_goal_count(self) -> int:
        """
        Return the number of completed goals in this result.

        This is a read-only aggregation over GoalResult objects.
        It does not decide whether a goal is complete.
        """

        return sum(
            1
            for goal in self.goals
            if goal.completed
        )

    # ------------------------------------------------------
    # Overall coverage
    # ------------------------------------------------------

    @property
    def overall_coverage(self) -> float:
        """
        Return the arithmetic mean of goal-level coverage.

        This property is a convenience view over the GoalResult
        values. It is not the canonical source of assessment
        coverage and should not be used by the assessment engine
        to make progression decisions.
        """

        if not self.goals:
            return 0.0

        return sum(
            goal.coverage
            for goal in self.goals
        ) / len(self.goals)

    # ------------------------------------------------------
    # Overall mastery
    # ------------------------------------------------------

    @property
    def overall_mastery(self) -> float:
        """
        Return the arithmetic mean of goal-level mastery.

        This is a reporting convenience only.

        The canonical mastery values remain owned by GoalState
        during assessment execution.
        """

        if not self.goals:
            return 0.0

        return sum(
            goal.mastery
            for goal in self.goals
        ) / len(self.goals)

    # ------------------------------------------------------
    # Overall confidence
    # ------------------------------------------------------

    @property
    def passed(self) -> bool:
        """
        Return the final academic pass/fail outcome.

        A result passes only when the completed assessment contains at
        least one goal and every goal was resolved successfully by the
        assessment/navigation layer. This is a read-only projection of
        the canonical goal completion state; it does not recalculate
        mastery, confidence, or thresholds.
        """

        return bool(self.goals) and all(
            goal.completed
            for goal in self.goals
        )

    # ------------------------------------------------------
    # Overall confidence
    # ------------------------------------------------------

    @property
    def overall_confidence(self) -> float:
        """
        Return the arithmetic mean of goal-level confidence.

        This is a reporting convenience only.

        The canonical confidence values remain owned by GoalState
        during assessment execution.
        """

        if not self.goals:
            return 0.0

        return sum(
            goal.confidence
            for goal in self.goals
        ) / len(self.goals)

