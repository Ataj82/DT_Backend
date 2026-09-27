"""
app/assessment/outcome_models.py

Compatibility models for the legacy outcome-based assessment layer.

IMPORTANT
---------
The current assessment architecture uses:

    GoalState
        |
        +-- IndicatorState
        +-- OutcomeEvidence
        |
        +-- CoverageEngine
        +-- OutcomeManager

The canonical evidence implementation lives in:

    app.assessment.evidence

This module intentionally keeps only the legacy outcome models that
are still required by older state consumers.

It does NOT define OutcomeEvidence again.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import OutcomeEvidence


# ==========================================================
# Legacy Performance Indicator
# ==========================================================


@dataclass(slots=True)
class PerformanceIndicator:
    """
    Legacy outcome-based performance indicator.

    This model is retained for compatibility with the older
    OutcomeState / AssessmentState implementation.

    New assessment code should prefer:

        app.assessment.goal_state.IndicatorState
    """

    id: str

    description: str

    bloom_level: str

    required: bool = True

    weight: float = 1.0

    attempts: int = 0


# ==========================================================
# Legacy Outcome State
# ==========================================================


@dataclass(slots=True)
class OutcomeState:
    """
    Legacy outcome-based assessment state.

    This object is retained only for compatibility with the older
    AssessmentState implementation.

    The current interview runtime should use GoalState instead.
    """

    outcome_id: str

    indicators: dict[str, PerformanceIndicator]

    evidence: list[OutcomeEvidence] = field(
        default_factory=list
    )

    coverage_score: float = 0.0

    mastery_score: float = 0.0

    confidence: float = 0.0

    target_mastery: float = 0.70

    min_confidence: float = 0.70

    completed: bool = False

    current_indicator_id: str | None = None

    # ======================================================
    # Indicator Access
    # ======================================================

    def get_indicator(
        self,
        indicator_id: str,
    ) -> PerformanceIndicator | None:
        """
        Return an indicator by normalized ID.
        """

        normalized_id = str(
            indicator_id or ""
        ).strip()

        if not normalized_id:
            return None

        return self.indicators.get(
            normalized_id
        )

    def require_indicator(
        self,
        indicator_id: str,
    ) -> PerformanceIndicator:
        """
        Return an indicator or raise a clear error.
        """

        indicator = self.get_indicator(
            indicator_id
        )

        if indicator is None:
            raise KeyError(
                f"Indicator '{indicator_id}' "
                f"does not exist in outcome "
                f"'{self.outcome_id}'."
            )

        return indicator

    # ======================================================
    # Registration
    # ======================================================

    def add_indicator(
        self,
        indicator: PerformanceIndicator,
    ) -> None:
        """
        Register one performance indicator.
        """

        if indicator is None:
            raise ValueError(
                "indicator cannot be None."
            )

        indicator_id = str(
            indicator.id or ""
        ).strip()

        if not indicator_id:
            raise ValueError(
                "indicator.id cannot be empty."
            )

        self.indicators[indicator_id] = indicator

    # ======================================================
    # Evidence
    # ======================================================

    def add_evidence(
        self,
        evidence: OutcomeEvidence,
    ) -> None:
        """
        Append evaluated evidence.
        """

        if evidence is None:
            raise ValueError(
                "evidence cannot be None."
            )

        indicator_id = str(
            evidence.indicator_id or ""
        ).strip()

        self.require_indicator(
            indicator_id
        )

        self.evidence.append(
            evidence
        )

    # ======================================================
    # Runtime Indicator
    # ======================================================

    def set_current_indicator(
        self,
        indicator_id: str | None,
    ) -> None:
        """
        Set the active indicator.
        """

        if indicator_id is None:
            self.current_indicator_id = None
            return

        normalized_id = str(
            indicator_id
        ).strip()

        if not normalized_id:
            raise ValueError(
                "indicator_id cannot be empty."
            )

        self.require_indicator(
            normalized_id
        )

        self.current_indicator_id = (
            normalized_id
        )

    def clear_current_indicator(
        self,
    ) -> None:
        """
        Clear the active indicator.
        """

        self.current_indicator_id = None

    # ======================================================
    # Completion
    # ======================================================

    def mark_completed(
        self,
    ) -> None:
        """
        Mark this legacy outcome as academically completed.
        """

        self.completed = True

    def reset(
        self,
    ) -> None:
        """
        Reset runtime outcome state.
        """

        self.coverage_score = 0.0
        self.mastery_score = 0.0
        self.confidence = 0.0
        self.completed = False
        self.current_indicator_id = None

        self.evidence.clear()

        for indicator in self.indicators.values():
            indicator.attempts = 0