"""
app/assessment/evidence_planner.py

Evidence Planner.

Selects the next indicator that should be assessed during an
interview session.

Responsibilities
----------------
- Filter assessable indicators.
- Determine whether more evidence is required.
- Optionally restrict selection to a preferred subset.
- Rank candidates using InformationGainPlanner.
- Return an indicator that belongs to the supplied GoalState.

Non-responsibilities
--------------------
- Mutating GoalState.
- Mutating IndicatorState.
- Evaluating answers.
- Calculating mastery.
- Calculating confidence.
- Recording evidence.
- Advancing goals.
- Persisting assessment state.

EvidencePlanner is intentionally stateless with respect to
assessment runtime state.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from .goal_state import GoalState, IndicatorState


class EvidencePlanner:
    """
    Stateless planner responsible for selecting the next indicator.

    The planner owns evidence-based candidate eligibility.

    It does not:
        - activate an indicator
        - change attempt counts
        - update evidence
        - calculate mastery
        - calculate confidence
        - complete a goal
        - advance to another goal
        - persist assessment state
    """

    DEFAULT_CONFIDENCE_THRESHOLD = 0.70
    DEFAULT_EVIDENCE_THRESHOLD = 0.70

    # v9.6: coverage-balance policy. These values affect only ordinary
    # next-indicator selection; remediation keeps the existing utility
    # path so an explicit retry request remains authoritative.
    UNASSESSED_COVERAGE_BONUS = 0.65
    REQUIRED_UNASSESSED_BONUS = 0.15
    REPEAT_ATTEMPT_PENALTY = 0.05
    REPEAT_ATTEMPT_SATURATION = 3

    # v10.3: human-like remediation guard. Repeated non-demonstration
    # answers on the same indicator are bounded so the interviewer does
    # not ask essentially the same remediation loop indefinitely. This
    # affects remediation selection only; ordinary evidence eligibility
    # and all scoring semantics remain unchanged.
    MAX_CONSECUTIVE_NON_DEMONSTRATION = 3

    def __init__(
        self,
        *,
        information_gain_planner: Any,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        evidence_threshold: float = DEFAULT_EVIDENCE_THRESHOLD,
        max_attempts_per_indicator: int | None = None,
    ) -> None:
        """
        Initialize the evidence planner.

        An indicator remains eligible until the evaluator has supplied
        sufficiently strong confidence *and* evidence. Attempt count is
        historical analytics only and never controls eligibility.
        """

        if information_gain_planner is None:
            raise ValueError(
                "EvidencePlanner requires an information_gain_planner."
            )

        self.confidence_threshold = self._probability(
            confidence_threshold,
            field_name="confidence_threshold",
        )
        self.evidence_threshold = self._probability(
            evidence_threshold,
            field_name="evidence_threshold",
        )
        # Deprecated compatibility argument. Attempts are historical
        # assessment telemetry and never control adaptive eligibility.
        self.max_attempts_per_indicator = None
        self.information_gain_planner = information_gain_planner

    # ==========================================================
    # Public API
    # ==========================================================

    def select_next_indicator(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
    ) -> IndicatorState | None:
        """
        Select the highest-utility currently assessable indicator.

        Candidate eligibility is determined entirely by ``candidates()``.
        Ranking is delegated to InformationGainPlanner.

        The returned object is the actual IndicatorState owned by
        ``goal_state``.
        """

        self._require_goal_state(goal_state)

        candidates = self.candidates(
            goal_state,
            preferred=preferred,
        )

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda indicator: self._selection_utility(
                goal_state,
                indicator,
            ),
        )

    def select_remediation_indicator(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
        max_attempts_per_indicator: int | None = None,
    ) -> IndicatorState | None:
        """Select an indicator for bounded remediation.

        An indicator with strong evidence can still represent mastery below
        the goal threshold. In that case the interviewer must be able to
        probe the same indicator again rather than incorrectly exhausting
        the goal after one question. Remediation is bounded by
        Historical attempt counts are not a stopping rule; the interview
        deadline is the hard boundary.
        """
        self._require_goal_state(goal_state)
        candidates = self.remediation_candidates(
            goal_state,
            preferred=preferred,
        )
        if not candidates:
            return None
        return max(candidates, key=lambda indicator: self._utility(goal_state, indicator))

    # ==========================================================
    # Candidate Selection
    # ==========================================================

    def candidates(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
    ) -> list[IndicatorState]:
        """
        Return all currently assessable indicators.

        Eligibility rules:

        1. Indicator must have a stable ID.
        2. If ``preferred`` is supplied, its ID must be included.
        3. Indicator must still require evidence.

        An assessed indicator is considered evidence-sufficient when both
        confidence and evidence strength meet their thresholds. Mastery
        level does not determine evidence sufficiency: strong evidence of
        low mastery is still a valid stopping point.

        No indicator or goal state is mutated.
        """

        self._require_goal_state(goal_state)

        indicators = self._goal_indicators(goal_state)

        if not indicators:
            return []

        preferred_ids = self._normalize_preferred_ids(
            preferred
        )

        candidates: list[IndicatorState] = []

        for indicator in indicators:
            indicator_id = self._indicator_id(indicator)

            if indicator_id is None:
                continue

            if (
                preferred_ids is not None
                and indicator_id not in preferred_ids
            ):
                continue

            if not self.can_assess(indicator):
                continue

            candidates.append(indicator)

        return candidates

    def remediation_candidates(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
        max_attempts_per_indicator: int | None = None,
    ) -> list[IndicatorState]:
        """Return indicators eligible for additional mastery evidence."""
        self._require_goal_state(goal_state)
        preferred_ids = self._normalize_preferred_ids(preferred)
        candidates: list[IndicatorState] = []
        for indicator in self._goal_indicators(goal_state):
            indicator_id = self._indicator_id(indicator)
            if indicator_id is None:
                continue
            if preferred_ids is not None and indicator_id not in preferred_ids:
                continue
            if getattr(indicator, "achievement_level", None) is None:
                continue

            # v10.3: avoid an unrealistic infinite remediation loop when
            # the learner repeatedly provides no usable evidence (for
            # example, "sorry", "I don't know", or "pass"). Evidence
            # remains valid historical data; we only stop selecting this
            # indicator for further remediation after a bounded consecutive
            # non-demonstration streak. This lets navigation move on to
            # another indicator/goal instead of consuming the whole session.
            if self._consecutive_non_demonstrations(
                goal_state,
                indicator_id,
            ) >= self.MAX_CONSECUTIVE_NON_DEMONSTRATION:
                continue

            candidates.append(indicator)
        return candidates


    def _consecutive_non_demonstrations(
        self,
        goal_state: GoalState,
        indicator_id: str,
    ) -> int:
        """Return the latest consecutive non-demonstration evidence count.

        OutcomeEvidence is stored chronologically by OutcomeManager. The
        helper is deliberately defensive for restored/legacy state and
        never mutates assessment state.
        """
        evidence_items = getattr(goal_state, "evidence", None) or []
        streak = 0
        for evidence in reversed(list(evidence_items)):
            if str(getattr(evidence, "indicator_id", "")).strip() != str(indicator_id).strip():
                continue
            if bool(getattr(evidence, "indicator_demonstrated", False)):
                break
            streak += 1
        return streak

    # ==========================================================
    # Retry Policy
    # ==========================================================

    def can_assess(
        self,
        indicator: IndicatorState,
    ) -> bool:
        """
        Return whether additional evidence is required.

        Unassessed indicators are eligible. Once both confidence and
        evidence strength reach their thresholds, questioning that
        indicator stops regardless of its historical attempt count.
        """

        self._require_indicator(indicator)

        achievement = getattr(indicator, "achievement_level", None)
        if achievement is None:
            return True

        confidence = self._probability(
            getattr(indicator, "confidence", None),
            field_name="confidence",
            default=0.0,
        )
        evidence = self._probability(
            getattr(indicator, "evidence_strength", None),
            field_name="evidence_strength",
            default=0.0,
        )

        return not (
            confidence >= self.confidence_threshold
            and evidence >= self.evidence_threshold
        )

    def exhausted(
        self,
        indicator: IndicatorState,
    ) -> bool:
        """
        Return whether the indicator has sufficient evidence.
        """

        return not self.can_assess(indicator)

    def remaining_attempts(
        self,
        indicator: IndicatorState,
    ) -> int:
        """
        Return a compatibility value for remaining evidence work.

        ``0`` means evidence is sufficient; ``1`` means another question
        may be useful. There is deliberately no attempt budget.
        """

        return 1 if self.can_assess(indicator) else 0

    # ==========================================================
    # Convenience
    # ==========================================================

    def has_candidates(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
    ) -> bool:
        """
        Return True when at least one assessable indicator exists.
        """

        return bool(
            self.candidates(
                goal_state,
                preferred=preferred,
            )
        )

    def candidate_count(
        self,
        goal_state: GoalState,
        *,
        preferred: Iterable[str] | str | None = None,
    ) -> int:
        """
        Return the number of currently assessable indicators.
        """

        return len(
            self.candidates(
                goal_state,
                preferred=preferred,
            )
        )

    # ==========================================================
    # v9.6 Coverage Optimization
    # ==========================================================

    def _selection_utility(
        self,
        goal_state: GoalState,
        indicator: IndicatorState,
    ) -> float:
        """Return the ordinary-selection utility with coverage balancing.

        v9.5 evidence quality answers *whether more evidence is needed*.
        v9.6 answers *where to spend that evidence budget next*.

        The existing InformationGainPlanner remains the base ranking
        signal. This layer adds a small deterministic coverage policy:

        * prefer indicators that have not yet been assessed;
        * give required, unassessed indicators an additional priority;
        * gently de-prioritize indicators that have already consumed
          several attempts, without ever making them ineligible.

        This is deliberately a ranking policy, not a stopping rule.
        Remediation selection continues to use ``_utility`` unchanged.
        """

        base = self._utility(goal_state, indicator)
        if not math.isfinite(base):
            return base

        score = base

        if not self._is_assessed(indicator):
            score += self.UNASSESSED_COVERAGE_BONUS

            if self._is_required(indicator):
                score += self.REQUIRED_UNASSESSED_BONUS

        attempts = self._attempts(indicator)
        if attempts > 0:
            saturation = min(
                attempts,
                self.REPEAT_ATTEMPT_SATURATION,
            ) / self.REPEAT_ATTEMPT_SATURATION
            score -= self.REPEAT_ATTEMPT_PENALTY * saturation

        if not math.isfinite(score):
            return float("-inf")

        return float(score)

    @staticmethod
    def _is_assessed(
        indicator: IndicatorState,
    ) -> bool:
        """Return canonical assessment state for coverage planning.

        Achievement level, rather than attempt count, determines whether
        an indicator has actually been assessed.
        """

        return getattr(indicator, "achievement_level", None) is not None

    @staticmethod
    def _is_required(
        indicator: IndicatorState,
    ) -> bool:
        value = getattr(indicator, "required", True)
        return value is True

    # ==========================================================
    # Information Gain
    # ==========================================================

    def _utility(
        self,
        goal_state: GoalState,
        indicator: IndicatorState,
    ) -> float:
        """
        Obtain the ranking utility from InformationGainPlanner.

        EvidencePlanner does not calculate information gain itself.

        A planner without a usable ``utility`` method cannot rank a
        candidate and therefore receives negative infinity.
        """

        utility_method = getattr(
            self.information_gain_planner,
            "utility",
            None,
        )

        if not callable(utility_method):
            return float("-inf")

        try:
            utility = utility_method(
                goal_state,
                indicator,
            )
        except (TypeError, ValueError):
            return float("-inf")

        return self._numeric_utility(utility)

    @staticmethod
    def _numeric_utility(
        value: Any,
    ) -> float:
        """
        Normalize a ranking utility into a finite float.

        Invalid, boolean, or non-finite values cannot win candidate
        selection and are therefore represented as negative infinity.
        """

        if value is None or isinstance(value, bool):
            return float("-inf")

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return float("-inf")

        if not math.isfinite(numeric):
            return float("-inf")

        return numeric

    # ==========================================================
    # GoalState Access
    # ==========================================================

    @staticmethod
    def _goal_indicators(
        goal_state: GoalState,
    ) -> list[IndicatorState]:
        """
        Return indicators owned by GoalState.

        The canonical GoalState representation is a mapping:

            dict[str, IndicatorState]

        An iterable fallback is retained for compatibility.
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

        if isinstance(indicators, Iterable):
            return [
                indicator
                for indicator in indicators
                if indicator is not None
            ]

        return []

    # ==========================================================
    # Preferred IDs
    # ==========================================================

    @staticmethod
    def _normalize_preferred_ids(
        preferred: Iterable[str] | str | None,
    ) -> set[str] | None:
        """
        Normalize preferred indicator IDs.

        Semantics:

            None
                No restriction.

            ""
                Explicitly empty preferred set.

            "indicator-a"
                One preferred indicator.

            iterable
                Set of preferred indicator IDs.

        Only string IDs are accepted. Arbitrary objects are not
        converted into identifiers.
        """

        if preferred is None:
            return None

        if isinstance(preferred, str):
            value = preferred.strip()

            return {value} if value else set()

        try:
            iterator = iter(preferred)
        except TypeError as exc:
            raise ValueError(
                "preferred must be an iterable of indicator IDs."
            ) from exc

        normalized: set[str] = set()

        for indicator_id in iterator:
            if indicator_id is None:
                continue

            if not isinstance(indicator_id, str):
                raise ValueError(
                    "preferred must contain only string indicator IDs."
                )

            value = indicator_id.strip()

            if value:
                normalized.add(value)

        return normalized

    # ==========================================================
    # Indicator Identity
    # ==========================================================

    @staticmethod
    def _indicator_id(
        indicator: Any,
    ) -> str | None:
        """
        Return the canonical indicator ID.

        ``id`` is the canonical IndicatorState identity.

        ``indicator_id`` is retained only as a compatibility
        fallback for older representations.

        Arbitrary values are never stringified into IDs.
        """

        if indicator is None:
            return None

        if isinstance(indicator, str):
            value = indicator.strip()

            return value or None

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

        if not isinstance(indicator_id, str):
            return None

        value = indicator_id.strip()

        return value or None

    @staticmethod
    def _probability(
        value: Any,
        *,
        field_name: str,
        default: float | None = None,
    ) -> float:
        if value is None:
            if default is not None:
                return default
            raise ValueError(f"{field_name} must be a number.")
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be a number.")
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a number.") from exc
        if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
            raise ValueError(f"{field_name} must be between 0 and 1.")
        return normalized

    # ==========================================================
    # Attempts
    # ==========================================================

    @staticmethod
    def _attempts(
        indicator: IndicatorState,
    ) -> int:
        """
        Read and normalize the runtime attempt count.

        Invalid, boolean, or negative values are treated as zero.

        This method never mutates the indicator.
        """

        value = getattr(
            indicator,
            "attempts",
            0,
        )

        if isinstance(value, bool):
            return 0

        if not isinstance(value, int):
            return 0

        return max(0, value)

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _require_goal_state(
        goal_state: GoalState,
    ) -> None:
        """
        Validate the supplied GoalState.
        """

        if goal_state is None:
            raise ValueError(
                "EvidencePlanner requires a goal_state."
            )

    @staticmethod
    def _require_indicator(
        indicator: IndicatorState,
    ) -> None:
        """
        Validate the supplied indicator.
        """

        if indicator is None:
            raise ValueError(
                "EvidencePlanner requires an indicator."
            )

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

        if not isinstance(indicator_id, str):
            raise ValueError(
                "Indicator requires a valid string id."
            )

        if not indicator_id.strip():
            raise ValueError(
                "Indicator requires a valid string id."
            )