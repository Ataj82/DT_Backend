"""
app/assessment/assessment_snapshot.py

Immutable derived assessment metrics.

AssessmentSnapshot is the canonical read-only result produced by
CoverageEngine for one GoalState.

It contains only derived assessment information.

It does NOT:
- evaluate learner answers
- calculate mastery
- calculate coverage
- calculate confidence
- mutate GoalState
- select indicators
- make progression decisions
- persist assessment state
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class AssessmentSnapshot:
    """
    Immutable derived assessment metrics for one goal.

    Values are normalized probabilities:

        coverage   -> 0.0 .. 1.0
        mastery    -> 0.0 .. 1.0
        confidence -> 0.0 .. 1.0

    ``missing_required`` contains the IDs of required indicators
    that have not yet been assessed.
    """

    coverage: float
    mastery: float
    confidence: float

    completed: bool

    missing_required: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "coverage",
            self._normalize_metric(
                self.coverage,
                field_name="coverage",
            ),
        )

        object.__setattr__(
            self,
            "mastery",
            self._normalize_metric(
                self.mastery,
                field_name="mastery",
            ),
        )

        object.__setattr__(
            self,
            "confidence",
            self._normalize_metric(
                self.confidence,
                field_name="confidence",
            ),
        )

        if not isinstance(
            self.completed,
            bool,
        ):
            raise ValueError(
                "completed must be a boolean."
            )

        object.__setattr__(
            self,
            "missing_required",
            self._normalize_missing_required(
                self.missing_required
            ),
        )

    # ==========================================================
    # Derived Queries
    # ==========================================================

    @property
    def remaining_required(self) -> int:
        """
        Return the number of required indicators still unassessed.
        """

        return len(self.missing_required)

    @property
    def has_missing_required(self) -> bool:
        """
        Return whether required indicators remain unassessed.
        """

        return bool(
            self.missing_required
        )

    # ==========================================================
    # Serialization
    # ==========================================================

    def to_dict(self) -> dict[str, object]:
        """
        Return a JSON-serializable representation.
        """

        return {
            "coverage": self.coverage,
            "mastery": self.mastery,
            "confidence": self.confidence,
            "completed": self.completed,
            "missing_required": list(
                self.missing_required
            ),
        }

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _normalize_metric(
        value: Any,
        *,
        field_name: str,
    ) -> float:
        """
        Validate and normalize a derived metric.

        Metrics must already represent probabilities in [0, 1].
        This method validates transport data; it does not calculate
        or derive metrics.
        """

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                f"{field_name} must be numeric."
            )

        if not isinstance(
            value,
            (int, float),
        ):
            raise ValueError(
                f"{field_name} must be numeric."
            )

        numeric = float(value)

        if not isfinite(numeric):
            raise ValueError(
                f"{field_name} must be finite."
            )

        if not 0.0 <= numeric <= 1.0:
            raise ValueError(
                f"{field_name} must be between 0.0 and 1.0."
            )

        return numeric

    @staticmethod
    def _normalize_missing_required(
        value: Any,
    ) -> tuple[str, ...]:
        """
        Normalize required-indicator IDs.

        IDs are preserved in their supplied order and duplicates are
        removed.
        """

        if value is None:
            return ()

        if isinstance(
            value,
            str,
        ):
            values = [value]
        else:
            try:
                values = list(value)
            except TypeError as exc:
                raise ValueError(
                    "missing_required must be an iterable of strings."
                ) from exc

        normalized: list[str] = []
        seen: set[str] = set()

        for item in values:
            if not isinstance(
                item,
                str,
            ):
                raise ValueError(
                    "Each missing_required entry must be a string."
                )

            indicator_id = item.strip()

            if not indicator_id:
                raise ValueError(
                    "missing_required cannot contain empty IDs."
                )

            if indicator_id in seen:
                continue

            seen.add(indicator_id)
            normalized.append(indicator_id)

        return tuple(normalized)