"""
app/assessment/progress_reasoner.py

Pure assessment progression reasoner.

ProgressReasoner reads GoalState and CoverageEngine's canonical
AssessmentSnapshot, then decides what assessment action should
happen next.

Responsibilities
----------------
- Read the canonical CoverageEngine assessment snapshot.
- Determine the next assessment status.
- Request indicator selection from EvidencePlanner.
- Produce an immutable GoalDecision.
- Apply configured mastery and confidence thresholds.

Non-responsibilities
--------------------
- Evaluating learner answers.
- Calculating coverage.
- Calculating mastery.
- Calculating confidence.
- Calculating completion.
- Selecting indicators directly.
- Mutating GoalState.
- Mutating IndicatorState.
- Recording evidence.
- Advancing goals.
- Persisting assessment state.

Architecture
------------
The progression flow is:

    GoalState
        |
        v
    CoverageEngine.snapshot()
        |
        v
    AssessmentSnapshot
        |
        v
    ProgressReasoner
        |
        +--> EvidencePlanner
        |       |
        |       v
        |   next indicator
        |
        v
    GoalDecision

CoverageEngine remains the canonical source for:

- coverage
- mastery
- confidence
- completion
- indicator weakness

EvidencePlanner remains the canonical source for indicator
selection.

GoalDecision remains the immutable output contract.
"""

from __future__ import annotations

import math
from typing import Any

from .decision import DecisionStatus, GoalDecision


class ProgressReasoner:
    """
    Stateless decision engine for one assessment goal.

    ProgressReasoner consumes the canonical AssessmentSnapshot
    produced by CoverageEngine and determines the next assessment
    action.

    It never mutates assessment runtime state.
    """

    DEFAULT_TARGET_MASTERY = 0.70
    DEFAULT_MIN_CONFIDENCE = 0.70

    def __init__(
        self,
        *,
        coverage_engine: Any,
        evidence_planner: Any,
    ) -> None:
        """
        Initialize the progression reasoner.

        Parameters
        ----------
        coverage_engine:
            Component responsible for producing the canonical
            assessment snapshot.

        evidence_planner:
            Component responsible for selecting the next assessable
            indicator.
        """

        if coverage_engine is None:
            raise ValueError(
                "ProgressReasoner requires a coverage_engine."
            )

        if evidence_planner is None:
            raise ValueError(
                "ProgressReasoner requires an evidence_planner."
            )

        self.coverage_engine = coverage_engine
        self.evidence_planner = evidence_planner

    # ==========================================================
    # Public API
    # ==========================================================

    def evaluate(
        self,
        goal_state: Any,
    ) -> GoalDecision:
        """
        Decide what assessment action should happen next.

        Decision priority
        -----------------
        1. Missing GoalState -> FAILED
        2. Missing snapshot -> FAILED
        3. CoverageEngine completed -> COMPLETE
        4. Required indicators remain -> COLLECT_EVIDENCE
        5. Confidence below threshold -> REDUCE_UNCERTAINTY
        6. Mastery below threshold -> REMEDIATE
        7. Goal is not complete and no indicator remains -> FAILED
        8. Otherwise -> CONTINUE

        ProgressReasoner does not calculate coverage, mastery,
        confidence, or completion.

        All derived metrics and completion state come directly from
        CoverageEngine's canonical AssessmentSnapshot.
        """

        # ------------------------------------------------------
        # GoalState
        # ------------------------------------------------------

        if goal_state is None:
            return self._decision(
                status=DecisionStatus.FAILED,
                reason="No goal state is available.",
                indicator=None,
                coverage=0.0,
                mastery=0.0,
                confidence=0.0,
            )

        # ------------------------------------------------------
        # Canonical snapshot
        # ------------------------------------------------------

        snapshot = self._snapshot(
            goal_state
        )

        if snapshot is None:
            return self._decision(
                status=DecisionStatus.FAILED,
                reason=(
                    "CoverageEngine returned no "
                    "assessment snapshot."
                ),
                indicator=None,
                coverage=0.0,
                mastery=0.0,
                confidence=0.0,
            )

        # ------------------------------------------------------
        # Canonical metrics
        # ------------------------------------------------------
        #
        # AssessmentSnapshot is already validated by its own
        # contract. ProgressReasoner must consume these values
        # directly rather than recalculating, clamping, or repairing
        # them.
        # ------------------------------------------------------

        coverage = snapshot.coverage
        mastery = snapshot.mastery
        confidence = snapshot.confidence

        # ------------------------------------------------------
        # Canonical completion
        # ------------------------------------------------------
        #
        # CoverageEngine owns completion.
        # ProgressReasoner must not independently infer completion.
        # ------------------------------------------------------

        if snapshot.completed:
            return self._decision(
                status=DecisionStatus.COMPLETE,
                reason=(
                    "Assessment requirements are satisfied."
                ),
                indicator=None,
                coverage=coverage,
                mastery=mastery,
                confidence=confidence,
            )

        # ------------------------------------------------------
        # Required indicators
        # ------------------------------------------------------
        #
        # AssessmentSnapshot guarantees that missing_required is an
        # immutable tuple of canonical indicator IDs.
        # ------------------------------------------------------

        missing_required = snapshot.missing_required

        if missing_required:
            indicator = self._select_indicator(
                goal_state,
                preferred=list(
                    missing_required
                ),
            )

            if indicator is None:
                return self._decision(
                    status=DecisionStatus.FAILED,
                    reason=(
                        "Required indicators remain "
                        "unassessed, but no assessable "
                        "required indicator is available."
                    ),
                    indicator=None,
                    coverage=coverage,
                    mastery=mastery,
                    confidence=confidence,
                )

            return self._decision(
                status=DecisionStatus.COLLECT_EVIDENCE,
                reason=(
                    "Required indicators remain "
                    "unassessed."
                ),
                indicator=indicator,
                coverage=coverage,
                mastery=mastery,
                confidence=confidence,
            )

        # ------------------------------------------------------
        # Confidence
        # ------------------------------------------------------
        #
        # Confidence is evaluated before mastery.
        #
        # If confidence is insufficient, additional evidence should
        # first reduce uncertainty rather than immediately entering
        # remediation.
        # ------------------------------------------------------

        min_confidence = self._min_confidence(
            goal_state
        )

        if confidence < min_confidence:
            indicator = self._select_indicator(
                goal_state
            )

            if indicator is None:
                return self._decision(
                    status=DecisionStatus.FAILED,
                    reason=(
                        "Confidence is below the required "
                        "threshold and no additional "
                        "assessment indicator is available."
                    ),
                    indicator=None,
                    coverage=coverage,
                    mastery=mastery,
                    confidence=confidence,
                )

            return self._decision(
                status=DecisionStatus.REDUCE_UNCERTAINTY,
                reason=(
                    "Additional evidence is required "
                    "to increase assessment confidence."
                ),
                indicator=indicator,
                coverage=coverage,
                mastery=mastery,
                confidence=confidence,
            )

        # ------------------------------------------------------
        # Mastery
        # ------------------------------------------------------

        target_mastery = self._target_mastery(
            goal_state
        )

        if mastery < target_mastery:
            weakest = self._weakest_indicators(
                goal_state
            )

            preferred = [
                indicator_id
                for indicator_id in (
                    self._indicator_id(indicator)
                    for indicator in weakest
                )
                if indicator_id is not None
            ]

            # --------------------------------------------------
            # Ask EvidencePlanner to select from the weakest
            # indicators first.
            #
            # ProgressReasoner does not itself decide which
            # indicator is assessable.
            # --------------------------------------------------

            # Mastery below target is a remediation condition, not
            # automatic goal failure. EvidencePlanner's ordinary
            # candidate policy intentionally stops re-questioning an
            # indicator once confidence/evidence are strong, but that
            # would terminate a low-mastery indicator after one answer.
            # Use the bounded remediation policy instead.
            indicator = self._indicator_id(
                self.evidence_planner.select_remediation_indicator(
                    goal_state,
                    preferred=preferred or None,
                )
            )

            # The weakest indicators may be exhausted; fall back to any
            # indicator that still has remediation attempts available.
            if indicator is None and preferred:
                indicator = self._indicator_id(
                    self.evidence_planner.select_remediation_indicator(
                        goal_state
                    )
                )

            if indicator is None:
                return self._decision(
                    status=DecisionStatus.FAILED,
                    reason=(
                        "Mastery is below the required "
                        "threshold and no additional "
                        "assessment indicator is available."
                    ),
                    indicator=None,
                    coverage=coverage,
                    mastery=mastery,
                    confidence=confidence,
                )

            return self._decision(
                status=DecisionStatus.REMEDIATE,
                reason=(
                    "Mastery is below the target; "
                    "additional evidence is required."
                ),
                indicator=indicator,
                coverage=coverage,
                mastery=mastery,
                confidence=confidence,
            )

        # ------------------------------------------------------
        # Continue gathering evidence
        # ------------------------------------------------------
        #
        # CoverageEngine already reported completed=False.
        #
        # No completion inference happens here.
        # ------------------------------------------------------

        indicator = self._select_indicator(
            goal_state
        )

        if indicator is None:
            return self._decision(
                status=DecisionStatus.FAILED,
                reason=(
                    "The goal is not complete according "
                    "to CoverageEngine, and no additional "
                    "assessment indicator is available."
                ),
                indicator=None,
                coverage=coverage,
                mastery=mastery,
                confidence=confidence,
            )

        return self._decision(
            status=DecisionStatus.CONTINUE,
            reason="Continue gathering assessment evidence.",
            indicator=indicator,
            coverage=coverage,
            mastery=mastery,
            confidence=confidence,
        )

    # ==========================================================
    # Coverage Snapshot
    # ==========================================================

    def _snapshot(
        self,
        goal_state: Any,
    ) -> Any:
        """
        Retrieve the canonical CoverageEngine snapshot.

        CoverageEngine owns:

        - coverage calculation
        - mastery calculation
        - confidence calculation
        - completion determination

        ProgressReasoner only consumes the resulting snapshot.
        """

        snapshot_method = getattr(
            self.coverage_engine,
            "snapshot",
            None,
        )

        if not callable(snapshot_method):
            raise TypeError(
                "coverage_engine must provide a callable "
                "snapshot(goal_state) method."
            )

        return snapshot_method(
            goal_state
        )

    # ==========================================================
    # Weakest Indicators
    # ==========================================================

    def _weakest_indicators(
        self,
        goal_state: Any,
    ) -> list[Any]:
        """
        Ask CoverageEngine for the weakest indicators.

        CoverageEngine remains responsible for determining
        indicator weakness.

        If the optional helper is unavailable or returns malformed
        data, an empty collection is returned.

        EvidencePlanner remains responsible for determining whether
        the preferred indicators are actually assessable.
        """

        weakest_method = getattr(
            self.coverage_engine,
            "weakest_indicators",
            None,
        )

        if not callable(
            weakest_method
        ):
            return []

        try:
            weakest = weakest_method(
                goal_state,
                limit=3,
            )
        except (
            TypeError,
            ValueError,
        ):
            return []

        if weakest is None:
            return []

        if isinstance(
            weakest,
            str,
        ):
            normalized = weakest.strip()

            return (
                [normalized]
                if normalized
                else []
            )

        try:
            return [
                indicator
                for indicator in weakest
                if indicator is not None
            ]
        except TypeError:
            return []

    # ==========================================================
    # Indicator Selection
    # ==========================================================

    def _select_indicator(
        self,
        goal_state: Any,
        *,
        preferred: list[str] | None = None,
    ) -> str | None:
        """
        Request the next indicator from EvidencePlanner.

        ProgressReasoner never selects an indicator itself.

        EvidencePlanner remains responsible for:

        - candidate eligibility
        - evidence-sufficiency eligibility
        - preferred-subset filtering
        - information-gain ranking

        The returned value is normalized to a canonical indicator ID.
        """

        select = getattr(
            self.evidence_planner,
            "select_next_indicator",
            None,
        )

        if not callable(select):
            raise TypeError(
                "evidence_planner must provide a callable "
                "select_next_indicator(...) method."
            )

        selected = select(
            goal_state,
            preferred=preferred,
        )

        return self._indicator_id(
            selected
        )

    # ==========================================================
    # Thresholds
    # ==========================================================

    @classmethod
    def _target_mastery(
        cls,
        goal_state: Any,
    ) -> float:
        """
        Resolve the configured mastery target.

        The underlying Goal configuration is preferred.
        GoalState's property remains a compatibility fallback.

        Threshold resolution is configuration handling, not
        assessment metric calculation.
        """

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        value = getattr(
            goal,
            "target_mastery",
            None,
        )

        if value is None:
            value = getattr(
                goal_state,
                "target_mastery",
                None,
            )

        return cls._threshold(
            value,
            default=cls.DEFAULT_TARGET_MASTERY,
        )

    @classmethod
    def _min_confidence(
        cls,
        goal_state: Any,
    ) -> float:
        """
        Resolve the configured minimum confidence threshold.

        The underlying Goal configuration is preferred.
        GoalState's property remains a compatibility fallback.

        Threshold resolution is configuration handling, not
        confidence calculation.
        """

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        value = getattr(
            goal,
            "min_confidence",
            None,
        )

        if value is None:
            value = getattr(
                goal_state,
                "min_confidence",
                None,
            )

        return cls._threshold(
            value,
            default=cls.DEFAULT_MIN_CONFIDENCE,
        )

    @staticmethod
    def _threshold(
        value: Any,
        *,
        default: float,
    ) -> float:
        """
        Normalize a configured threshold into [0, 1].

        Invalid values fall back to the supplied default.

        Boolean values are rejected because True/False are not
        meaningful assessment thresholds.
        """

        if isinstance(
            value,
            bool,
        ):
            return default

        try:
            numeric = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return default

        if not math.isfinite(
            numeric
        ):
            return default

        return max(
            0.0,
            min(
                1.0,
                numeric,
            ),
        )

    # ==========================================================
    # Indicator Normalization
    # ==========================================================

    @staticmethod
    def _indicator_id(
        indicator: Any,
    ) -> str | None:
        """
        Resolve a canonical indicator ID.

        ``id`` is the canonical runtime identity.

        ``indicator_id`` remains a compatibility fallback for
        older representations.

        Arbitrary objects are never coerced into indicator IDs.
        """

        if indicator is None:
            return None

        if isinstance(
            indicator,
            str,
        ):
            normalized = indicator.strip()

            return (
                normalized
                if normalized
                else None
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

        if not isinstance(
            indicator_id,
            str,
        ):
            return None

        normalized = indicator_id.strip()

        return (
            normalized
            if normalized
            else None
        )

    # ==========================================================
    # Decision Construction
    # ==========================================================

    @staticmethod
    def _decision(
        *,
        status: str,
        reason: str,
        indicator: str | None,
        coverage: float,
        mastery: float,
        confidence: float,
    ) -> GoalDecision:
        """
        Construct the immutable canonical GoalDecision.

        All decision construction is centralized here so the
        ProgressReasoner cannot accidentally return inconsistent
        decision objects.

        Metrics originate from AssessmentSnapshot and are passed
        through unchanged.
        """

        return GoalDecision(
            status=status,
            reason=reason,
            next_indicator=indicator,
            coverage=coverage,
            mastery=mastery,
            confidence=confidence,
        )