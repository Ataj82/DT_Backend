"""
app/assessment/goal_state.py

Runtime state for assessing a single Goal.

A GoalState tracks:

- current indicator
- collected evidence
- indicator progress
- mastery
- confidence
- completion
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any


# ==========================================================
# Indicator State
# ==========================================================

@dataclass(slots=True)
class IndicatorState:
    """
    Runtime state for one indicator.
    """

    id: str

    description: str

    bloom_level: int

    required: bool = True

    attempts: int = 0

    demonstrated: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ==========================================================
# Goal State
# ==========================================================

@dataclass(slots=True)
class GoalState:
    """
    Runtime assessment state for one Goal.
    """

    goal: Any

    indicators: dict[str, IndicatorState]

    evidence: list[Any] = field(
        default_factory=list
    )

    current_indicator_id: str | None = None

    completed: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ======================================================
    # Indicator Helpers
    # ======================================================

    @property
    def current_indicator(self) -> IndicatorState | None:

        if self.current_indicator_id is None:
            return None

        return self.indicators.get(
            self.current_indicator_id
        )

    def set_current_indicator(
        self,
        indicator_id: str | None,
    ) -> None:

        self.current_indicator_id = indicator_id

    # ======================================================
    # Evidence
    # ======================================================

    def add_evidence(
        self,
        evidence: Any,
    ) -> None:

        self.evidence.append(evidence)

        indicator = self.indicators.get(
            evidence.indicator_id
        )

        if indicator is None:
            return

        indicator.attempts += 1

        demonstrated = getattr(
            evidence,
            "indicator_demonstrated",
            False,
        )

        if not demonstrated:

            demonstrated = (
                getattr(
                    evidence,
                    "achieved_level",
                    0,
                )
                >= 3
            )

        if demonstrated:

            indicator.demonstrated = True

    # ======================================================
    # Statistics
    # ======================================================

    def coverage(self) -> float:

        if not self.indicators:
            return 0.0

        covered = sum(

            1

            for indicator

            in self.indicators.values()

            if indicator.demonstrated

        )

        return covered / len(self.indicators)

    def mastery(self) -> float:

        if not self.evidence:
            return 0.0

        return mean(

            getattr(
                evidence,
                "achieved_level",
                0.0,
            )

            for evidence

            in self.evidence

        )

    def confidence(self) -> float:

        if not self.evidence:
            return 0.0

        return mean(

            getattr(
                evidence,
                "confidence",
                0.0,
            )

            for evidence

            in self.evidence

        )

    # ======================================================
    # Completion
    # ======================================================

    def mark_completed(
        self,
    ) -> None:

        self.completed = True

    # ======================================================
    # Convenience
    # ======================================================

    @property
    def remaining_indicators(
        self,
    ) -> list[IndicatorState]:

        return [

            indicator

            for indicator

            in self.indicators.values()

            if not indicator.demonstrated

        ]

    @property
    def completed_indicators(
        self,
    ) -> list[IndicatorState]:

        return [

            indicator

            for indicator

            in self.indicators.values()

            if indicator.demonstrated

        ]