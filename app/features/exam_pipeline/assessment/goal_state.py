"""
app/assessment/goal_state.py

Mutable runtime assessment state for one learning goal.

GoalState is the single source of truth for assessment state during
one assessment/interview session.

It owns:
- indicator runtime state
- evidence
- current indicator
- goal terminal state

It does not:
- evaluate answers
- calculate metrics
- select indicators
- calculate mastery
- calculate confidence
- navigate goals

Assessment-state semantics
---------------------------
An indicator that has not yet been assessed uses ``None`` for
assessment metrics:

    achievement_level = None
    confidence = None
    evidence_strength = None

Once an indicator has been assessed, the assessment layer supplies
authoritative values.

Achievement level is an ordinal 1..6 value.

``None`` is the only unassessed sentinel for achievement_level.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable


# ==========================================================
# Goal Status
# ==========================================================

GOAL_STATUS_PENDING = "pending"
GOAL_STATUS_PASSED = "passed"
GOAL_STATUS_FAILED = "failed"


# ==========================================================
# Indicator Runtime State
# ==========================================================


@dataclass(slots=True)
class IndicatorState:
    """
    Mutable runtime state for one goal indicator.

    Configuration:
        id
        description
        bloom_level
        weight
        required

    Runtime:
        attempts
        demonstrated
        achievement_level
        confidence
        evidence_strength
        feedback
    """

    id: str
    description: str
    bloom_level: str

    weight: float = 1.0
    required: bool = True

    attempts: int = 0
    demonstrated: bool = False

    # None means not assessed.
    achievement_level: float | None = None

    # None means not assessed.
    confidence: float | None = None

    # None means not assessed.
    evidence_strength: float | None = None

    # Adaptive difficulty state. The value is the difficulty requested
    # for the next question on this indicator, in [0, 1].
    difficulty: float = 0.5
    difficulty_history: list[float] = field(default_factory=list)
    difficulty_performance_history: list[float] = field(default_factory=list)
    last_difficulty_reason: str = "initial"

    feedback: str = ""

    @property
    def assessed(self) -> bool:
        """
        Return whether this indicator has been attempted.

        Attempt count is the authoritative runtime signal for
        assessment state.
        """

        return self.attempts > 0

    @property
    def achieved(self) -> bool:
        """
        Return the evaluator-supplied demonstrated state.

        This property does not calculate achievement.
        """

        return self.demonstrated

    def reset(self) -> None:
        """
        Reset all assessment-specific runtime state.
        """

        self.attempts = 0
        self.demonstrated = False
        self.achievement_level = None
        self.confidence = None
        self.evidence_strength = None
        self.difficulty = 0.5
        self.difficulty_history.clear()
        self.difficulty_performance_history.clear()
        self.last_difficulty_reason = "initial"
        self.feedback = ""


# ==========================================================
# Goal Runtime State
# ==========================================================


@dataclass(slots=True)
class GoalState:
    """
    Mutable runtime state for one learning goal.
    """

    goal: object

    completed: bool = False
    resolved: bool = False
    failed: bool = False

    status: str = GOAL_STATUS_PENDING

    evidence: list[Any] = field(
        default_factory=list
    )

    indicators: dict[str, IndicatorState] = field(
        default_factory=dict
    )

    current_indicator_id: str | None = None

    # Goal-specific time-management snapshot. These values are runtime
    # bookkeeping only; GoalTimeManager remains the calculation owner.
    time_budget_seconds: float = 0.0
    time_started_at: str | None = None
    time_finished_at: str | None = None
    time_elapsed_seconds: float = 0.0
    time_remaining_seconds: float = 0.0
    time_outcome: str | None = None

    # ======================================================
    # Initialization
    # ======================================================

    def __post_init__(self) -> None:
        if self.goal is None:
            raise ValueError(
                "GoalState requires a goal."
            )

        goal_indicators = getattr(
            self.goal,
            "indicators",
            None,
        )

        if goal_indicators is None:
            return

        for indicator in self._iter_goal_indicators(
            goal_indicators
        ):
            indicator_id = self._normalize_id(
                getattr(
                    indicator,
                    "id",
                    None,
                )
            )

            if indicator_id is None:
                raise ValueError(
                    "Goal indicator requires a valid id."
                )

            if indicator_id in self.indicators:
                raise ValueError(
                    f"Duplicate indicator id "
                    f"'{indicator_id}' in goal "
                    f"'{self.goal_id}'."
                )

            self.indicators[indicator_id] = (
                self._create_indicator_state(
                    indicator,
                    goal_bloom_level=getattr(
                        self.goal,
                        "bloom_level",
                        "",
                    ),
                    goal_difficulty=getattr(
                        self.goal,
                        "difficulty",
                        0.5,
                    ),
                )
            )

        self._normalize_indicator_mapping()
        self._normalize_current_indicator()

    # ======================================================
    # Initialization Helpers
    # ======================================================

    @staticmethod
    def _iter_goal_indicators(
        goal_indicators: Any,
    ) -> Iterable[Any]:
        """
        Support both mapping-like and iterable indicator collections.
        """

        values = getattr(
            goal_indicators,
            "values",
            None,
        )

        if callable(values):
            return values()

        if isinstance(
            goal_indicators,
            Iterable,
        ):
            return goal_indicators

        return ()

    def _normalize_indicator_mapping(self) -> None:
        """
        Normalize indicator IDs and preserve IndicatorState objects.
        """

        normalized: dict[str, IndicatorState] = {}

        for key, state in self.indicators.items():
            indicator_id = self._normalize_id(
                getattr(
                    state,
                    "id",
                    None,
                )
            )

            if indicator_id is None:
                indicator_id = self._normalize_id(
                    key
                )

            if indicator_id is None:
                continue

            if indicator_id in normalized:
                raise ValueError(
                    f"Duplicate indicator id "
                    f"'{indicator_id}'."
                )

            normalized[indicator_id] = state

        self.indicators = normalized

    def _normalize_current_indicator(self) -> None:
        """
        Ensure the current indicator ID is valid.
        """

        if self.current_indicator_id is None:
            return

        current_id = self._normalize_id(
            self.current_indicator_id
        )

        if (
            current_id is None
            or current_id not in self.indicators
        ):
            self.current_indicator_id = None
        else:
            self.current_indicator_id = current_id

    @staticmethod
    def _normalize_id(
        value: Any,
    ) -> str | None:
        """
        Normalize an identifier to a non-empty string.
        """

        if value is None:
            return None

        normalized = str(
            value
        ).strip()

        return normalized or None

    @classmethod
    def _create_indicator_state(
            cls,
            indicator: Any,
            *,
            goal_bloom_level: Any = "",
        goal_difficulty: Any = 0.5,
    ) -> IndicatorState:
        """
        Create runtime state from an indicator definition.

        Assessment values always begin unassessed.
        """

        indicator_id = cls._normalize_id(
            getattr(
                indicator,
                "id",
                None,
            )
        )

        if indicator_id is None:
            raise ValueError(
                "GoalIndicator requires a valid id."
            )

        description = (
            getattr(
                indicator,
                "description",
                None,
            )
            or getattr(
                indicator,
                "name",
                None,
            )
            or indicator_id
        )

        try:
            weight = float(
                getattr(
                    indicator,
                    "weight",
                    1.0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            weight = 1.0

        if weight < 0.0:
            weight = 0.0

        difficulty = getattr(indicator, "difficulty", None)
        if difficulty is None:
            difficulty = getattr(indicator, "initial_difficulty", None)
        if difficulty is None:
            extra = getattr(indicator, "model_extra", None)
            if isinstance(extra, dict):
                difficulty = extra.get("difficulty")
        if difficulty is None:
            difficulty = goal_difficulty
        try:
            normalized_difficulty = max(0.0, min(1.0, float(difficulty if difficulty is not None else 0.5)))
        except (TypeError, ValueError):
            normalized_difficulty = 0.5

        return IndicatorState(
            id=indicator_id,
            description=str(description),
            bloom_level=str(
                getattr(indicator, "bloom_level", None)
                or goal_bloom_level
                or ""
            ),
            weight=weight,
            required=bool(getattr(indicator, "required", True)),
            difficulty=normalized_difficulty,
            difficulty_history=[normalized_difficulty],
        )
    # ======================================================
    # Goal Configuration
    # ======================================================

    @property
    def goal_id(self) -> str | None:
        """
        Return the normalized goal ID.
        """

        return self._normalize_id(
            getattr(
                self.goal,
                "id",
                None,
            )
        )

    @property
    def target_mastery(self) -> float:
        """
        Return the configured goal mastery threshold.

        GoalState does not calculate mastery.
        """

        try:
            value = float(
                getattr(
                    self.goal,
                    "target_mastery",
                    0.70,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.70

        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

    @property
    def min_confidence(self) -> float:
        """
        Return the configured goal confidence threshold.

        GoalState does not calculate confidence.
        """

        try:
            value = float(
                getattr(
                    self.goal,
                    "min_confidence",
                    0.70,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.70

        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

    # ======================================================
    # Indicator Access
    # ======================================================

    def get_indicator(
        self,
        indicator_id: str,
    ) -> IndicatorState | None:
        """
        Return an indicator by normalized ID.
        """

        normalized_id = self._normalize_id(
            indicator_id
        )

        if normalized_id is None:
            return None

        return self.indicators.get(
            normalized_id
        )

    def require_indicator(
        self,
        indicator_id: str,
    ) -> IndicatorState:
        """
        Return an indicator or raise KeyError.
        """

        normalized_id = self._normalize_id(
            indicator_id
        )

        if normalized_id is None:
            raise KeyError(
                "Indicator ID cannot be empty."
            )

        indicator = self.get_indicator(
            normalized_id
        )

        if indicator is None:
            raise KeyError(
                f"Indicator '{normalized_id}' "
                f"does not exist in goal "
                f"'{self.goal_id}'."
            )

        return indicator

    @property
    def current_indicator(
        self,
    ) -> IndicatorState | None:
        """
        Return the selected indicator.
        """

        if self.current_indicator_id is None:
            return None

        return self.get_indicator(
            self.current_indicator_id
        )

    def set_current_indicator(
        self,
        indicator_id: str | None,
    ) -> None:
        """
        Select an existing indicator.
        """

        if indicator_id is None:
            self.current_indicator_id = None
            return

        normalized_id = self._normalize_id(
            indicator_id
        )

        if normalized_id is None:
            raise ValueError(
                "Indicator ID cannot be empty."
            )

        self.require_indicator(
            normalized_id
        )

        self.current_indicator_id = normalized_id

    def clear_current_indicator(self) -> None:
        """
        Clear the selected indicator.
        """

        self.current_indicator_id = None

    # ======================================================
    # Evidence
    # ======================================================

    def add_evidence(
        self,
        evidence: Any,
    ) -> None:
        """
        Append evidence to this goal.
        """

        if evidence is None:
            raise ValueError(
                "Cannot add None evidence."
            )

        self.evidence.append(
            evidence
        )

    def evidence_for_turn(
        self,
        *,
        turn_index: int,
        indicator_id: str | None = None,
    ) -> Any | None:
        """Return the evidence committed for one exact interview turn.

        Turn identity is preferred over list position or latest-indicator
        lookup. This keeps historical evidence correct when the same
        indicator is attempted multiple times.
        """

        if isinstance(turn_index, bool) or not isinstance(turn_index, int):
            raise ValueError("turn_index must be an integer.")

        normalized_indicator_id = self._normalize_id(indicator_id)

        for evidence in reversed(self.evidence):
            evidence_turn_index = getattr(evidence, "turn_index", None)
            if evidence_turn_index != turn_index:
                continue

            if normalized_indicator_id is None:
                return evidence

            evidence_indicator_id = self._normalize_id(
                getattr(evidence, "indicator_id", None)
            )
            if evidence_indicator_id == normalized_indicator_id:
                return evidence

        return None

    def add_evidence_for_indicator(
        self,
        *,
        indicator_id: str,
        evidence: Any,
    ) -> None:
        """
        Add evidence after validating indicator ownership.
        """

        if evidence is None:
            raise ValueError(
                "Cannot add None evidence."
            )

        normalized_indicator_id = self._normalize_id(
            indicator_id
        )

        if normalized_indicator_id is None:
            raise ValueError(
                "Indicator ID cannot be empty."
            )

        self.require_indicator(
            normalized_indicator_id
        )

        evidence_indicator_id = self._normalize_id(
            getattr(
                evidence,
                "indicator_id",
                None,
            )
        )

        if (
            evidence_indicator_id
            != normalized_indicator_id
        ):
            raise ValueError(
                "Evidence indicator mismatch: "
                f"expected '{normalized_indicator_id}', "
                f"received '{evidence_indicator_id}'."
            )

        self.add_evidence(
            evidence
        )

    # ======================================================
    # Terminal State
    # ======================================================

    def mark_completed(self) -> None:
        """
        Mark this goal as successfully resolved.
        """

        self.completed = True
        self.resolved = True
        self.failed = False
        self.status = GOAL_STATUS_PASSED

    def mark_failed(self) -> None:
        """
        Mark this goal as failed.
        """

        self.completed = False
        self.resolved = True
        self.failed = True
        self.status = GOAL_STATUS_FAILED

    @property
    def is_resolved(self) -> bool:
        return self.resolved

    @property
    def is_failed(self) -> bool:
        return self.failed

    @property
    def is_pending(self) -> bool:
        return (
            not self.resolved
            and self.status == GOAL_STATUS_PENDING
        )

    # ======================================================
    # Inspection
    # ======================================================

    @property
    def indicator_count(self) -> int:
        return len(
            self.indicators
        )

    @property
    def assessed_indicator_count(self) -> int:
        return sum(
            indicator.assessed
            for indicator in self.indicators.values()
        )

    @property
    def required_indicators(
        self,
    ) -> list[IndicatorState]:
        return [
            indicator
            for indicator in self.indicators.values()
            if indicator.required
        ]

    @property
    def missing_required_indicators(
        self,
    ) -> list[IndicatorState]:
        return [
            indicator
            for indicator in self.required_indicators
            if not indicator.assessed
        ]

    @property
    def assessed_indicators(
        self,
    ) -> list[IndicatorState]:
        return [
            indicator
            for indicator in self.indicators.values()
            if indicator.assessed
        ]

    # ======================================================
    # Reset
    # ======================================================

    def reset(self) -> None:
        """
        Reset all runtime assessment state.
        """

        self.completed = False
        self.resolved = False
        self.failed = False
        self.status = GOAL_STATUS_PENDING

        self.evidence.clear()
        self.current_indicator_id = None
        self.time_budget_seconds = 0.0
        self.time_started_at = None
        self.time_finished_at = None
        self.time_elapsed_seconds = 0.0
        self.time_remaining_seconds = 0.0
        self.time_outcome = None

        for indicator in self.indicators.values():
            indicator.reset()

    # ======================================================
    # Clone
    # ======================================================

    def clone(self) -> "GoalState":
        """
        Return an independent deep copy.
        """

        return deepcopy(
            self
        )