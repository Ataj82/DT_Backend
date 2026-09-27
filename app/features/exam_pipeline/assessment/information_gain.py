"""
app/assessment/information_gain.py

Information Gain Planner.

InformationGainPlanner calculates a deterministic utility score
for assessment indicators.

Responsibilities
----------------
- Calculate deterministic indicator utility.
- Resolve indicator IDs to canonical IndicatorState objects.
- Rank indicators by utility.
- Return the highest-utility indicator.

Non-responsibilities
--------------------
- Selecting whether an indicator is assessable.
- Enforcing retry limits.
- Mutating GoalState.
- Mutating IndicatorState.
- Recording evidence.
- Evaluating learner answers.
- Calculating canonical mastery.
- Calculating canonical confidence.
- Advancing goals.
- Persisting assessment state.

Architecture
------------
InformationGainPlanner is intentionally stateless.

EvidencePlanner owns candidate eligibility and retry policy.

The flow is:

    GoalState
        |
        v
    EvidencePlanner
        |
        +--> candidate eligibility
        |
        v
    InformationGainPlanner
        |
        +--> utility()
        +--> rank()
        +--> best()
        |
        v
    IndicatorState
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


class InformationGainPlanner:
    """
    Stateless utility planner for assessment indicators.

    A higher utility score means that an indicator is considered
    more valuable to assess next.

    The planner never mutates GoalState or IndicatorState.
    """

    # ==========================================================
    # Heuristic Configuration
    # ==========================================================

    UNCERTAINTY_WEIGHT = 0.35
    MASTERY_GAP_WEIGHT = 0.30
    EVIDENCE_GAP_WEIGHT = 0.20
    IMPORTANCE_WEIGHT = 0.10
    DEMONSTRATED_BONUS_WEIGHT = 0.05

    DEMONSTRATED_BONUS = 0.50

    # ==========================================================
    # Public API
    # ==========================================================

    def utility(
        self,
        goal_state: Any,
        indicator: Any,
    ) -> float:
        """
        Calculate the relative utility of assessing ``indicator``.

        ``indicator`` may be:

        - an indicator ID
        - an IndicatorState-like object

        The canonical IndicatorState owned by ``goal_state`` is
        always preferred when the indicator can be resolved.

        The score is a relative ranking value and is not required
        to be normalized to [0, 1].
        """

        if goal_state is None:
            return 0.0

        indicator_state = self._resolve_indicator(
            goal_state,
            indicator,
        )

        if indicator_state is None:
            return 0.0

        confidence = self._normalized_metric(
            getattr(
                indicator_state,
                "confidence",
                0.0,
            )
        )

        achievement = self._normalized_metric(
            getattr(
                indicator_state,
                "achievement_level",
                0.0,
            )
        )

        weight = self._indicator_weight(
            indicator_state
        )

        demonstrated = self._demonstrated(
            indicator_state
        )

        target_mastery = self._target_mastery(
            goal_state
        )

        # ------------------------------------------------------
        # Utility components
        # ------------------------------------------------------

        uncertainty = max(
            0.0,
            1.0 - confidence,
        )

        mastery_gap = max(
            0.0,
            target_mastery - achievement,
        )

        # Evidence scarcity is driven by evidence strength, not attempts.
        evidence_strength = self._normalized_metric(
            getattr(indicator_state, "evidence_strength", 0.0)
        )
        evidence_gap = max(
            0.0,
            1.0 - evidence_strength,
        )

        importance = weight

        demonstrated_gap = (
            0.0
            if demonstrated
            else self.DEMONSTRATED_BONUS
        )

        score = (
            self.UNCERTAINTY_WEIGHT
            * uncertainty
            + self.MASTERY_GAP_WEIGHT
            * mastery_gap
            + self.EVIDENCE_GAP_WEIGHT
            * evidence_gap
            + self.IMPORTANCE_WEIGHT
            * importance
            + self.DEMONSTRATED_BONUS_WEIGHT
            * demonstrated_gap
        )

        if not math.isfinite(score):
            return 0.0

        return max(
            0.0,
            float(score),
        )

    # ==========================================================
    # Ranking
    # ==========================================================

    def rank(
        self,
        goal_state: Any,
        indicators: Iterable[Any] | None = None,
    ) -> list[Any]:
        """
        Return indicators ordered by decreasing utility.

        When ``indicators`` is omitted, all indicators belonging to
        ``goal_state`` are ranked.

        When supplied, the provided indicators are resolved to their
        canonical GoalState instances where possible.

        No runtime state is mutated.
        """

        if goal_state is None:
            return []

        if indicators is None:
            candidates = self._indicators(
                goal_state
            )
        else:
            candidates = self._resolve_candidates(
                goal_state,
                indicators,
            )

        return sorted(
            candidates,
            key=lambda indicator: self.utility(
                goal_state,
                indicator,
            ),
            reverse=True,
        )

    # ==========================================================
    # Best Indicator
    # ==========================================================

    def best(
        self,
        goal_state: Any,
        indicators: Iterable[Any] | None = None,
    ) -> Any | None:
        """
        Return the highest-utility indicator.

        Returns None when no indicators are available.
        """

        ranked = self.rank(
            goal_state,
            indicators,
        )

        if not ranked:
            return None

        return ranked[0]

    # ==========================================================
    # Indicator Resolution
    # ==========================================================

    @classmethod
    def _resolve_indicator(
        cls,
        goal_state: Any,
        indicator: Any,
    ) -> Any | None:
        """
        Resolve an indicator ID or IndicatorState-like object.

        Resolution always prefers the canonical object owned by
        GoalState.

        If an external indicator object cannot be resolved to a
        canonical GoalState indicator, None is returned.
        """

        if goal_state is None or indicator is None:
            return None

        indicator_id = cls._indicator_id(
            indicator
        )

        if indicator_id is None:
            return None

        # ------------------------------------------------------
        # Canonical GoalState lookup
        # ------------------------------------------------------

        get_indicator = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(get_indicator):
            resolved = get_indicator(
                indicator_id
            )

            if resolved is not None:
                return resolved

        # ------------------------------------------------------
        # Mapping fallback
        # ------------------------------------------------------

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if indicators is not None:
            values = getattr(
                indicators,
                "get",
                None,
            )

            if callable(values):
                resolved = values(
                    indicator_id
                )

                if resolved is not None:
                    return resolved

        return None

    @classmethod
    def _resolve_candidates(
        cls,
        goal_state: Any,
        indicators: Iterable[Any],
    ) -> list[Any]:
        """
        Resolve a supplied indicator collection to canonical
        GoalState indicator objects.

        Invalid or unresolvable indicators are ignored.
        """

        resolved: list[Any] = []

        for indicator in indicators:
            canonical = cls._resolve_indicator(
                goal_state,
                indicator,
            )

            if canonical is not None:
                resolved.append(
                    canonical
                )

        return resolved

    # ==========================================================
    # Indicator Collection
    # ==========================================================

    @staticmethod
    def _indicators(
        goal_state: Any,
    ) -> list[Any]:
        """
        Return the indicators owned by GoalState.

        The canonical representation is a mapping whose values are
        IndicatorState objects.

        Iterable compatibility is retained.
        """

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if indicators is None:
            return []

        values = getattr(
            indicators,
            "values",
            None,
        )

        if callable(values):
            return [
                indicator
                for indicator in values()
                if indicator is not None
            ]

        if isinstance(
            indicators,
            Iterable,
        ):
            return [
                indicator
                for indicator in indicators
                if indicator is not None
            ]

        return []

    # ==========================================================
    # Runtime State Helpers
    # ==========================================================

    @staticmethod
    def _attempt_count(
        indicator: Any,
    ) -> int:
        """
        Return a normalized non-negative attempt count.

        Invalid or boolean values are treated as zero.

        This method only reads state.
        """

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

        if not isinstance(
            value,
            int,
        ):
            return 0

        return max(
            0,
            value,
        )

    @staticmethod
    def _demonstrated(
        indicator: Any,
    ) -> bool:
        """
        Return the canonical demonstrated flag.

        Only actual booleans are trusted. Malformed values are
        treated as False rather than using Python truthiness such as:

            bool("false") == True
        """

        value = getattr(
            indicator,
            "demonstrated",
            False,
        )

        if not isinstance(
            value,
            bool,
        ):
            return False

        return value

    @staticmethod
    def _indicator_weight(
        indicator: Any,
    ) -> float:
        """
        Return a normalized non-negative indicator weight.

        Weight represents importance, not probability, so it is
        intentionally not clamped to 1.0.
        """

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
            weight = float(
                value
            )
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
    # Goal Configuration
    # ==========================================================

    @classmethod
    def _target_mastery(
        cls,
        goal_state: Any,
    ) -> float:
        """
        Resolve the configured mastery target.

        Goal configuration is the authority for the target.
        """

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        if goal is None:
            return 0.0

        target = getattr(
            goal,
            "target_mastery",
            0.0,
        )

        return cls._normalized_metric(
            target
        )

    # ==========================================================
    # Numeric Normalization
    # ==========================================================

    @staticmethod
    def _normalized_metric(
        value: Any,
    ) -> float:
        """
        Normalize a metric to [0, 1].

        Invalid, boolean, or non-finite values become 0.0.
        """

        if isinstance(
            value,
            bool,
        ):
            return 0.0

        try:
            numeric = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if not math.isfinite(
            numeric
        ):
            return 0.0

        return max(
            0.0,
            min(
                1.0,
                numeric,
            ),
        )

    # ==========================================================
    # Indicator Identity
    # ==========================================================

    @staticmethod
    def _indicator_id(
        indicator: Any,
    ) -> str | None:
        """
        Extract a stable indicator ID.

        ``id`` is canonical.

        ``indicator_id`` is retained as a compatibility fallback.

        Arbitrary objects are never converted into identifiers.
        """

        if isinstance(
            indicator,
            str,
        ):
            value = indicator.strip()

            return value or None

        if indicator is None:
            return None

        indicator_id = getattr(
            indicator,
            "id",
            None,
        )

        if indicator_id is None:
            indicator_id = getattr(
                indicator,
                "indicator_id",
                None,
            )

        if not isinstance(
            indicator_id,
            str,
        ):
            return None

        value = indicator_id.strip()

        return value or None