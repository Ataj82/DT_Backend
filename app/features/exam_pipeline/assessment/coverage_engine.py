"""
app/assessment/coverage_engine.py

Canonical, stateless assessment metrics engine.

CoverageEngine is the authority for derived assessment metrics:

- coverage
- mastery
- confidence
- completion
- missing required indicators
- indicator assessment state

It never mutates GoalState.

Assessment metric semantics
---------------------------
IndicatorState stores:

    achievement_level = None
        -> not assessed

    achievement_level = 1..6
        -> assessed achievement level

CoverageEngine converts achievement_level 1..6 into normalized
mastery 0..1.

Confidence is already represented as a probability in the range
0..1 and is normalized only for defensive aggregation.

No derived value is written back into GoalState.
"""

from __future__ import annotations

import math
from typing import Any

from .assessment_snapshot import AssessmentSnapshot
from .scoring_normalizer import ScoringNormalizer


class CoverageEngine:
    """
    Stateless authority for derived assessment metrics.

    CoverageEngine reads GoalState and produces derived metrics.
    It never mutates GoalState or IndicatorState.
    """

    DEFAULT_TARGET_MASTERY = 0.70
    DEFAULT_TARGET_CONFIDENCE = 0.70

    MIN_ACHIEVEMENT_LEVEL = 1
    MAX_ACHIEVEMENT_LEVEL = 6

    MIN_PROBABILITY = 0.0
    MAX_PROBABILITY = 1.0

    # ==========================================================
    # Snapshot
    # ==========================================================

    def snapshot(
        self,
        goal_state: Any,
    ) -> AssessmentSnapshot:
        """
        Produce the canonical derived assessment snapshot.

        Completion requires:

        1. Every required indicator has been assessed.
        2. Aggregate mastery meets the configured target.
        3. Aggregate confidence meets the configured target.

        Assessment state is determined by achievement_level, not
        attempt count.

        No state is mutated.
        """

        self._require_goal_state(goal_state)

        indicators = self._indicators(goal_state)

        # ------------------------------------------------------
        # Empty goal
        # ------------------------------------------------------

        if not indicators:
            return AssessmentSnapshot(
                coverage=1.0,
                mastery=0.0,
                confidence=0.0,
                completed=False,
                missing_required=(),
            )

        # ------------------------------------------------------
        # Coverage
        #
        # Coverage represents the proportion of all configured
        # indicators that have been assessed.
        # ------------------------------------------------------

        total = len(indicators)

        assessed = sum(
            1
            for indicator in indicators
            if self._is_assessed(indicator)
        )

        coverage = assessed / total

        # ------------------------------------------------------
        # Weighted mastery / confidence
        # ------------------------------------------------------

        total_weight = sum(
            self._weight(indicator)
            for indicator in indicators
        )

        if total_weight <= 0.0:
            mastery = 0.0
            confidence = 0.0
        else:
            # v9.7: normalize repeated evidence per indicator before
            # applying the configured indicator weights.  This makes the
            # final interview score independent of which repeated attempt
            # happened to be evaluated last.
            normalized = [
                ScoringNormalizer.indicator_snapshot(
                    goal_state,
                    indicator,
                )
                for indicator in indicators
            ]

            mastery = (
                sum(
                    normalized[index][0] * self._weight(indicator)
                    for index, indicator in enumerate(indicators)
                )
                / total_weight
            )

            confidence = (
                sum(
                    normalized[index][1] * self._weight(indicator)
                    for index, indicator in enumerate(indicators)
                )
                / total_weight
            )

        # ------------------------------------------------------
        # Required indicators
        # ------------------------------------------------------

        missing_required = tuple(
            self._indicator_id(indicator)
            for indicator in indicators
            if (
                self._is_required(indicator)
                and not self._is_assessed(indicator)
            )
        )

        # ------------------------------------------------------
        # Goal thresholds
        # ------------------------------------------------------

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        target_mastery = self._target(
            getattr(
                goal,
                "target_mastery",
                self.DEFAULT_TARGET_MASTERY,
            ),
            default=self.DEFAULT_TARGET_MASTERY,
        )

        target_confidence = self._target(
            getattr(
                goal,
                "min_confidence",
                self.DEFAULT_TARGET_CONFIDENCE,
            ),
            default=self.DEFAULT_TARGET_CONFIDENCE,
        )

        # ------------------------------------------------------
        # Completion
        # ------------------------------------------------------

        completed = (
            bool(indicators)
            and not missing_required
            and mastery >= target_mastery
            and confidence >= target_confidence
        )

        return AssessmentSnapshot(
            coverage=self._probability(coverage),
            mastery=self._probability(mastery),
            confidence=self._probability(confidence),
            completed=completed,
            missing_required=missing_required,
        )

    # ==========================================================
    # Mastery
    # ==========================================================

    @classmethod
    def achievement_to_mastery(
        cls,
        achievement_level: Any,
    ) -> float:
        """
        Convert a discrete achievement level 1..6 into mastery 0..1.

        Mapping:

            None -> 0.0
            1    -> 0.1667
            2    -> 0.3333
            3    -> 0.5
            4    -> 0.6667
            5    -> 0.8333
            6    -> 1.0

        CoverageEngine owns this normalization.

        Invalid achievement levels are rejected rather than silently
        clamped because achievement_level is an authoritative
        discrete semantic value.
        """

        if achievement_level is None:
            return 0.0

        level = cls._achievement_level(
            achievement_level
        )

        return (
            level
            / cls.MAX_ACHIEVEMENT_LEVEL
        )

    @classmethod
    def _evidence_strength(
        cls,
        indicator: Any,
    ) -> float:
        return cls._probability(
            getattr(indicator, "evidence_strength", 0.0)
        )

    @classmethod
    def _mastery(
        cls,
        indicator: Any,
    ) -> float:
        return cls.achievement_to_mastery(
            getattr(
                indicator,
                "achievement_level",
                None,
            )
        )

    # ==========================================================
    # Indicator Queries
    # ==========================================================

    def weakest_indicators(
        self,
        goal_state: Any,
        *,
        limit: int = 3,
    ) -> list[Any]:
        """
        Return weakest indicators first.

        Priority:

        1. lowest mastery
        2. lowest confidence
        3. lowest evidence strength

        This method only reads state.
        """

        self._require_goal_state(goal_state)

        if isinstance(limit, bool):
            raise ValueError(
                "limit must be a positive integer."
            )

        try:
            normalized_limit = int(limit)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "limit must be a positive integer."
            ) from exc

        if normalized_limit <= 0:
            return []

        indicators = self._indicators(
            goal_state
        )

        ordered = sorted(
            indicators,
            key=lambda indicator: (
                self._mastery(indicator),
                self._confidence(indicator),
                self._evidence_strength(indicator),
            ),
        )

        return ordered[:normalized_limit]

    def assessed_indicators(
        self,
        goal_state: Any,
    ) -> list[Any]:
        """
        Return indicators whose achievement level has been assessed.

        Assessment is determined by achievement_level, not attempts.
        """

        self._require_goal_state(goal_state)

        return [
            indicator
            for indicator in self._indicators(goal_state)
            if self._is_assessed(indicator)
        ]

    def unassessed_indicators(
        self,
        goal_state: Any,
    ) -> list[Any]:
        """
        Return indicators without an assessed achievement level.
        """

        self._require_goal_state(goal_state)

        return [
            indicator
            for indicator in self._indicators(goal_state)
            if not self._is_assessed(indicator)
        ]

    # ==========================================================
    # Canonical Completion
    # ==========================================================

    def is_complete(
        self,
        goal_state: Any,
    ) -> bool:
        """
        Return canonical goal completion.

        Completion is derived exclusively from the current snapshot.
        """

        return self.snapshot(
            goal_state
        ).completed

    # ==========================================================
    # Internal State Helpers
    # ==========================================================

    @staticmethod
    def _require_goal_state(
        goal_state: Any,
    ) -> None:
        if goal_state is None:
            raise ValueError(
                "CoverageEngine requires a goal_state."
            )

    @staticmethod
    def _indicators(
        goal_state: Any,
    ) -> list[Any]:
        """
        Return configured indicators without mutating GoalState.
        """

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if indicators is None:
            return []

        if isinstance(
            indicators,
            dict,
        ):
            return list(
                indicators.values()
            )

        try:
            return list(indicators)
        except TypeError as exc:
            raise TypeError(
                "GoalState indicators must be a mapping "
                "or iterable."
            ) from exc

    @classmethod
    def _is_assessed(
        cls,
        indicator: Any,
    ) -> bool:
        """
        Return whether an indicator has an authoritative assessment.

        IMPORTANT:
        attempts are historical interaction data.

        achievement_level is the canonical assessment-state signal.
        """

        achievement_level = getattr(
            indicator,
            "achievement_level",
            None,
        )

        return achievement_level is not None

    @staticmethod
    def _is_required(
        indicator: Any,
    ) -> bool:
        return bool(
            getattr(
                indicator,
                "required",
                True,
            )
        )

    @staticmethod
    def _indicator_id(
        indicator: Any,
    ) -> str:
        value = getattr(
            indicator,
            "id",
            None,
        )

        if not isinstance(
            value,
            str,
        ):
            raise ValueError(
                "Indicator must provide a string id."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Indicator id must be a non-empty string."
            )

        return normalized

    @staticmethod
    def _attempts(
        indicator: Any,
    ) -> int:
        value = getattr(
            indicator,
            "attempts",
            0,
        )

        if isinstance(
            value,
            bool,
        ):
            return 0

        try:
            numeric = int(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0

        return max(
            0,
            numeric,
        )

    @staticmethod
    def _weight(
        indicator: Any,
    ) -> float:
        value = getattr(
            indicator,
            "weight",
            1.0,
        )

        if isinstance(
            value,
            bool,
        ):
            return 1.0

        try:
            weight = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 1.0

        if not math.isfinite(weight):
            return 1.0

        return max(
            0.0,
            weight,
        )

    # ==========================================================
    # Probability
    # ==========================================================

    @classmethod
    def _confidence(
        cls,
        indicator: Any,
    ) -> float:
        return cls._probability(
            getattr(
                indicator,
                "confidence",
                None,
            )
        )

    @classmethod
    def _probability(
        cls,
        value: Any,
    ) -> float:
        """
        Normalize a probability-like value to [0, 1].

        This method must never be used to normalize achievement
        levels.
        """

        if value is None:
            return 0.0

        if isinstance(
            value,
            bool,
        ):
            return 0.0

        try:
            numeric = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if not math.isfinite(numeric):
            return 0.0

        return max(
            cls.MIN_PROBABILITY,
            min(
                cls.MAX_PROBABILITY,
                numeric,
            ),
        )

    # ==========================================================
    # Achievement Level
    # ==========================================================

    @classmethod
    def _achievement_level(
        cls,
        value: Any,
    ) -> int:
        """
        Validate a discrete achievement level.

        No mastery calculation occurs here.
        """

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        try:
            numeric = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            ) from exc

        if not math.isfinite(numeric):
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        if not numeric.is_integer():
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        level = int(numeric)

        if not (
            cls.MIN_ACHIEVEMENT_LEVEL
            <= level
            <= cls.MAX_ACHIEVEMENT_LEVEL
        ):
            raise ValueError(
                "achievement_level must be between "
                f"{cls.MIN_ACHIEVEMENT_LEVEL} and "
                f"{cls.MAX_ACHIEVEMENT_LEVEL}."
            )

        return level

    # ==========================================================
    # Goal Thresholds
    # ==========================================================

    @classmethod
    def _target(
        cls,
        value: Any,
        *,
        default: float,
    ) -> float:
        """
        Normalize a goal threshold to a finite value in [0, 1].

        Invalid configuration falls back to the canonical default.
        """

        if value is None:
            return default

        if isinstance(
            value,
            bool,
        ):
            return default

        try:
            numeric = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

        if not math.isfinite(numeric):
            return default

        return max(
            cls.MIN_PROBABILITY,
            min(
                cls.MAX_PROBABILITY,
                numeric,
            ),
        )