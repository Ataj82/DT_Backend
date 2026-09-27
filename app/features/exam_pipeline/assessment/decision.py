"""
app/assessment/decision.py

Immutable result of one assessment reasoning step.

GoalDecision is the canonical decision contract between the
assessment reasoning layer and the application/interview layer.

GoalDecision does NOT:
- evaluate answers
- calculate metrics
- mutate GoalState
- select indicators
- navigate goals
- persist state
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final


# ==========================================================
# Decision Status
# ==========================================================


class DecisionStatus:
    """
    Canonical assessment decision statuses.

    Values are intentionally plain strings so they remain compatible
    with API responses, persistence, logging, and application-layer
    callers.
    """

    COLLECT_EVIDENCE: Final[str] = "collect_evidence"
    REDUCE_UNCERTAINTY: Final[str] = "reduce_uncertainty"
    REMEDIATE: Final[str] = "remediate"
    CONTINUE: Final[str] = "continue"

    COMPLETE: Final[str] = "complete"
    FAILED: Final[str] = "failed"

    @classmethod
    def completion_statuses(cls) -> frozenset[str]:
        """
        Return statuses representing successful completion.
        """

        return frozenset({cls.COMPLETE})

    @classmethod
    def failure_statuses(cls) -> frozenset[str]:
        """
        Return statuses representing assessment failure.
        """

        return frozenset({cls.FAILED})

    @classmethod
    def progression_statuses(cls) -> frozenset[str]:
        """
        Return statuses that require continued assessment
        progression.
        """

        return frozenset(
            {
                cls.COLLECT_EVIDENCE,
                cls.REDUCE_UNCERTAINTY,
                cls.REMEDIATE,
                cls.CONTINUE,
            }
        )

    @classmethod
    def terminal_statuses(cls) -> frozenset[str]:
        """
        Return all terminal decision statuses.
        """

        return frozenset(
            {
                cls.COMPLETE,
                cls.FAILED,
            }
        )

    @classmethod
    def all_statuses(cls) -> frozenset[str]:
        """
        Return every valid assessment decision status.
        """

        return frozenset(
            {
                cls.COLLECT_EVIDENCE,
                cls.REDUCE_UNCERTAINTY,
                cls.REMEDIATE,
                cls.CONTINUE,
                cls.COMPLETE,
                cls.FAILED,
            }
        )


# ==========================================================
# Goal Decision
# ==========================================================


@dataclass(frozen=True, slots=True)
class GoalDecision:
    """
    Immutable result produced by assessment reasoning.

    Metrics are supplied by the assessment layer and are expected to
    already represent canonical [0, 1] values.

    GoalDecision validates and transports those values. It does not
    calculate, clamp, infer, or otherwise transform them.
    """

    status: str
    reason: str

    next_indicator: str | None = None

    coverage: float = 0.0
    mastery: float = 0.0
    confidence: float = 0.0

    def __post_init__(self) -> None:
        """
        Validate and normalize the structural decision contract.

        Because the dataclass is frozen, structural normalization uses
        object.__setattr__ during initialization only.
        """

        normalized_status = self._normalize_status(
            self.status
        )

        normalized_reason = self._normalize_reason(
            self.reason
        )

        normalized_indicator = self._normalize_indicator(
            self.next_indicator
        )

        object.__setattr__(
            self,
            "status",
            normalized_status,
        )

        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )

        object.__setattr__(
            self,
            "next_indicator",
            normalized_indicator,
        )

        self._validate_metric(
            self.coverage,
            "coverage",
        )

        self._validate_metric(
            self.mastery,
            "mastery",
        )

        self._validate_metric(
            self.confidence,
            "confidence",
        )

        if (
            normalized_status
            in DecisionStatus.completion_statuses()
            and normalized_indicator is not None
        ):
            raise ValueError(
                "A completed GoalDecision cannot contain "
                "a next_indicator."
            )

        if (
            normalized_status
            in DecisionStatus.failure_statuses()
            and normalized_indicator is not None
        ):
            raise ValueError(
                "A failed GoalDecision cannot contain "
                "a next_indicator."
            )

    # ======================================================
    # Semantic State
    # ======================================================

    @property
    def is_complete(self) -> bool:
        """
        Return whether this decision represents completion.
        """

        return self.status in DecisionStatus.completion_statuses()

    @property
    def is_failed(self) -> bool:
        """
        Return whether this decision represents failure.
        """

        return self.status in DecisionStatus.failure_statuses()

    @property
    def is_terminal(self) -> bool:
        """
        Return whether this decision is terminal.
        """

        return self.status in DecisionStatus.terminal_statuses()

    @property
    def is_progression(self) -> bool:
        """
        Return whether this decision requests continued assessment
        progression.
        """

        return self.status in DecisionStatus.progression_statuses()

    @property
    def requires_indicator(self) -> bool:
        """
        Return whether a next indicator is supplied.
        """

        return self.next_indicator is not None

    @property
    def should_continue(self) -> bool:
        """
        Return whether assessment may continue.

        Terminal decisions stop progression.
        """

        return not self.is_terminal

    # ======================================================
    # Serialization
    # ======================================================

    def to_dict(self) -> dict[str, object]:
        """
        Serialize the decision into the canonical application shape.
        """

        return {
            "status": self.status,
            "reason": self.reason,
            "next_indicator": self.next_indicator,
            "coverage": self.coverage,
            "mastery": self.mastery,
            "confidence": self.confidence,
        }

    # ======================================================
    # Normalization
    # ======================================================

    @staticmethod
    def _normalize_status(
        value: object,
    ) -> str:
        """
        Normalize and validate a decision status.
        """

        if not isinstance(value, str):
            raise ValueError(
                "GoalDecision status must be a string."
            )

        status = value.strip()

        if status not in DecisionStatus.all_statuses():
            raise ValueError(
                f"Unknown assessment decision status '{status}'."
            )

        return status

    @staticmethod
    def _normalize_reason(
        value: object,
    ) -> str:
        """
        Normalize and validate the decision reason.
        """

        if not isinstance(value, str):
            raise ValueError(
                "GoalDecision reason must be a string."
            )

        reason = value.strip()

        if not reason:
            raise ValueError(
                "GoalDecision reason is required."
            )

        return reason

    @staticmethod
    def _normalize_indicator(
        value: object,
    ) -> str | None:
        """
        Normalize an optional next-indicator identifier.

        None means that no next indicator is supplied.
        """

        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                "GoalDecision next_indicator must be a string "
                "or None."
            )

        normalized = value.strip()

        return normalized or None

    # ======================================================
    # Validation
    # ======================================================

    @staticmethod
    def _validate_metric(
        value: object,
        name: str,
    ) -> None:
        """
        Validate an assessment metric in the inclusive [0, 1] range.

        GoalDecision does not normalize or clamp metrics. An invalid
        upstream assessment result must fail loudly.
        """

        if isinstance(value, bool):
            raise ValueError(
                f"GoalDecision {name} must be numeric."
            )

        if not isinstance(value, (int, float)):
            raise ValueError(
                f"GoalDecision {name} must be numeric."
            )

        numeric = float(value)

        if not isfinite(numeric):
            raise ValueError(
                f"GoalDecision {name} must be finite."
            )

        if not 0.0 <= numeric <= 1.0:
            raise ValueError(
                f"GoalDecision {name} must be between "
                "0.0 and 1.0."
            )