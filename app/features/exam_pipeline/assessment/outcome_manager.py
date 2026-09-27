"""
app/assessment/outcome_manager.py

Canonical mutation boundary for assessment state.

OutcomeManager applies already-evaluated AnswerEvidence to GoalState.

Responsibilities
----------------
- Resolve the target IndicatorState.
- Validate evaluator evidence.
- Record one learner attempt.
- Apply evaluator-produced indicator values.
- Store evidence.
- Synchronize successful completion from CoverageEngine.

Non-responsibilities
--------------------
- Answer evaluation.
- Achievement calculation.
- Mastery calculation.
- Confidence calculation.
- Evidence-strength calculation.
- Indicator selection.
- Progression decisions.
- Failure/exhaustion decisions.
- Aggregate coverage calculation.

Architecture
------------

    AnswerEvidence
          |
          v
    OutcomeManager
          |
          +----> IndicatorState
          |
          +----> GoalState.evidence
          |
          v
    CoverageEngine
"""

from __future__ import annotations

import math
from typing import Any


class OutcomeManager:
    """
    Single mutation boundary for assessment runtime state.

    OutcomeManager accepts semantic evaluation results and applies
    them to the appropriate GoalState indicator.

    It never determines whether an incomplete goal should fail.
    """

    MIN_ACHIEVEMENT_LEVEL = 1
    MAX_ACHIEVEMENT_LEVEL = 6

    MIN_PROBABILITY = 0.0
    MAX_PROBABILITY = 1.0

    def __init__(
        self,
        *,
        coverage_engine: Any,
    ) -> None:
        if coverage_engine is None:
            raise ValueError(
                "OutcomeManager requires a coverage_engine."
            )

        if not callable(
            getattr(
                coverage_engine,
                "is_complete",
                None,
            )
        ):
            raise TypeError(
                "OutcomeManager requires a coverage_engine "
                "with a callable is_complete() method."
            )

        self.coverage_engine = coverage_engine

    # ==========================================================
    # Public Mutation API
    # ==========================================================

    def apply_evaluation(
        self,
        goal_state: Any,
        *,
        indicator_id: str,
        evidence: Any,
        turn_index: int | None = None,
    ) -> None:
        """
        Apply exactly one evaluated learner answer.

        The operation is:

            validate GoalState
                ↓
            resolve indicator
                ↓
            validate evidence
                ↓
            increment attempt
                ↓
            apply evidence
                ↓
            store evidence
                ↓
            synchronize successful completion

        The OutcomeManager does not decide failure/exhaustion.
        """

        self._require_goal_state(goal_state)

        normalized_indicator_id = (
            self._normalize_indicator_id(indicator_id)
        )

        self._validate_evidence(
            evidence=evidence,
            indicator_id=normalized_indicator_id,
        )

        self._validate_turn_identity(
            evidence=evidence,
            turn_index=turn_index,
        )

        indicator = self._resolve_indicator(
            goal_state=goal_state,
            indicator_id=normalized_indicator_id,
        )

        # ------------------------------------------------------
        # Prepare all evaluator values before mutation.
        # ------------------------------------------------------

        values = self._validated_evidence_values(
            evidence=evidence,
        )

        # ------------------------------------------------------
        # Mutation boundary.
        # ------------------------------------------------------

        before_attempts = self._normalize_attempts(
            getattr(indicator, "attempts", 0)
        )

        self._increment_attempt(
            indicator=indicator,
        )

        after_attempts = self._normalize_attempts(
            getattr(indicator, "attempts", 0)
        )

        if after_attempts != before_attempts + 1:
            raise RuntimeError(
                "Assessment attempt commit failed: expected attempts "
                f"to change from {before_attempts} to "
                f"{before_attempts + 1}, received {after_attempts}."
            )

        self._apply_indicator_values(
            indicator=indicator,
            values=values,
        )

        self._store_evidence(
            goal_state=goal_state,
            evidence=evidence,
        )

        self.refresh_completion(goal_state)

    def add_evidence(
        self,
        goal_state: Any,
        evidence: Any,
    ) -> None:
        """
        Store already-evaluated evidence without incrementing
        the learner attempt counter.

        This method is intended for restoration/import/replay
        scenarios.

        Normal learner evaluation should use apply_evaluation().
        """

        self._require_goal_state(goal_state)

        if evidence is None:
            raise ValueError(
                "OutcomeManager cannot add None evidence."
            )

        indicator_id = self._normalize_indicator_id(
            getattr(
                evidence,
                "indicator_id",
                None,
            )
        )

        self._validate_evidence(
            evidence=evidence,
            indicator_id=indicator_id,
        )

        indicator = self._resolve_indicator(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        values = self._validated_evidence_values(
            evidence=evidence,
        )

        self._apply_indicator_values(
            indicator=indicator,
            values=values,
        )

        self._store_evidence(
            goal_state=goal_state,
            evidence=evidence,
        )

        self.refresh_completion(goal_state)

    # ==========================================================
    # Indicator State
    # ==========================================================

    def update_indicator(
        self,
        goal_state: Any,
        *,
        indicator_id: str,
        achievement_level: int,
        confidence: float,
        evidence_strength: float,
        demonstrated: bool,
        feedback: str = "",
    ) -> None:
        """
        Persist authoritative evaluator values on an indicator.

        No assessment metric is calculated here.
        """

        self._require_goal_state(goal_state)

        normalized_indicator_id = (
            self._normalize_indicator_id(indicator_id)
        )

        indicator = self._resolve_indicator(
            goal_state=goal_state,
            indicator_id=normalized_indicator_id,
        )

        values = {
            "achievement_level": (
                self._normalize_achievement_level(
                    achievement_level
                )
            ),
            "confidence": (
                self._normalize_probability(
                    confidence,
                    field_name="confidence",
                )
            ),
            "evidence_strength": (
                self._normalize_probability(
                    evidence_strength,
                    field_name="evidence_strength",
                )
            ),
            "demonstrated": (
                self._normalize_demonstrated(
                    demonstrated
                )
            ),
            "feedback": (
                self._normalize_feedback(
                    feedback
                )
            ),
        }

        self._apply_indicator_values(
            indicator=indicator,
            values=values,
        )

    # ==========================================================
    # Attempts
    # ==========================================================

    def record_attempt(
        self,
        goal_state: Any,
        indicator_id: str,
    ) -> None:
        """
        Record exactly one learner attempt.
        """

        self._require_goal_state(goal_state)

        normalized_indicator_id = (
            self._normalize_indicator_id(indicator_id)
        )

        indicator = self._resolve_indicator(
            goal_state=goal_state,
            indicator_id=normalized_indicator_id,
        )

        self._increment_attempt(
            indicator=indicator,
        )

    @classmethod
    def _increment_attempt(
        cls,
        *,
        indicator: Any,
    ) -> None:
        current = getattr(
            indicator,
            "attempts",
            0,
        )

        attempts = cls._normalize_attempts(
            current
        )

        indicator.attempts = attempts + 1

    # ==========================================================
    # Completion
    # ==========================================================

    def refresh_completion(
        self,
        goal_state: Any,
    ) -> bool:
        """
        Synchronize successful completion from CoverageEngine.

        Important:

        - CoverageEngine owns successful completion.
        - OutcomeManager never converts incomplete -> failed.
        - Existing explicit failure/resolution is preserved.
        """

        self._require_goal_state(goal_state)

        completed = bool(
            self.coverage_engine.is_complete(
                goal_state
            )
        )

        if not completed:
            return False

        mark_completed = getattr(
            goal_state,
            "mark_completed",
            None,
        )

        if not callable(mark_completed):
            raise RuntimeError(
                "GoalState must provide mark_completed()."
            )

        mark_completed()

        return True

    def mark_completed(
        self,
        goal_state: Any,
    ) -> None:
        """
        Explicitly mark successful completion.

        Normal assessment completion should preferably flow through
        CoverageEngine + refresh_completion().
        """

        self._require_goal_state(goal_state)

        mark_completed = getattr(
            goal_state,
            "mark_completed",
            None,
        )

        if not callable(mark_completed):
            raise RuntimeError(
                "GoalState must provide mark_completed()."
            )

        mark_completed()

    def mark_failed(
        self,
        goal_state: Any,
    ) -> None:
        """
        Explicitly mark a goal as failed/exhausted.

        This method exists as a state-mutation primitive.

        The decision to call it belongs to the progression/decision
        layer, not OutcomeManager.
        """

        self._require_goal_state(goal_state)

        mark_failed = getattr(
            goal_state,
            "mark_failed",
            None,
        )

        if not callable(mark_failed):
            raise RuntimeError(
                "GoalState must provide mark_failed()."
            )

        mark_failed()

    # ==========================================================
    # Reset
    # ==========================================================

    def reset(
        self,
        goal_state: Any,
    ) -> None:
        self._require_goal_state(goal_state)

        reset = getattr(
            goal_state,
            "reset",
            None,
        )

        if not callable(reset):
            raise RuntimeError(
                "GoalState must provide reset()."
            )

        reset()

    # ==========================================================
    # Clone
    # ==========================================================

    def clone(
        self,
        goal_state: Any,
    ) -> Any:
        self._require_goal_state(goal_state)

        clone = getattr(
            goal_state,
            "clone",
            None,
        )

        if not callable(clone):
            raise RuntimeError(
                "GoalState must provide clone()."
            )

        return clone()

    # ==========================================================
    # Indicator Resolution
    # ==========================================================

    @classmethod
    def _resolve_indicator(
        cls,
        *,
        goal_state: Any,
        indicator_id: str,
    ) -> Any:
        cls._require_goal_state(goal_state)

        normalized_indicator_id = (
            cls._normalize_indicator_id(
                indicator_id
            )
        )

        require_indicator = getattr(
            goal_state,
            "require_indicator",
            None,
        )

        if callable(require_indicator):
            try:
                indicator = require_indicator(
                    normalized_indicator_id
                )
            except (
                KeyError,
                LookupError,
            ) as exc:
                raise ValueError(
                    cls._unknown_indicator_message(
                        goal_state,
                        normalized_indicator_id,
                    )
                ) from exc

            if indicator is not None:
                return indicator

        get_indicator = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(get_indicator):
            try:
                indicator = get_indicator(
                    normalized_indicator_id
                )
            except (
                KeyError,
                LookupError,
            ):
                indicator = None

            if indicator is not None:
                return indicator

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if isinstance(indicators, dict):
            indicator = indicators.get(
                normalized_indicator_id
            )

            if indicator is not None:
                return indicator

        if indicators is not None:
            try:
                for candidate in indicators:
                    candidate_id = (
                        cls._extract_indicator_id(
                            candidate
                        )
                    )

                    if candidate_id == normalized_indicator_id:
                        return candidate
            except TypeError:
                pass

        raise ValueError(
            cls._unknown_indicator_message(
                goal_state,
                normalized_indicator_id,
            )
        )

    @classmethod
    def _unknown_indicator_message(
        cls,
        goal_state: Any,
        indicator_id: str,
    ) -> str:
        goal_id = getattr(
            goal_state,
            "goal_id",
            None,
        )

        if callable(goal_id):
            goal_id = goal_id()

        if goal_id is None:
            goal = getattr(
                goal_state,
                "goal",
                None,
            )

            goal_id = getattr(
                goal,
                "id",
                None,
            )

        if goal_id is None:
            return f"Unknown indicator '{indicator_id}'."

        return (
            f"Unknown indicator '{indicator_id}' "
            f"for goal '{goal_id}'."
        )

    @classmethod
    def _require_indicator(
        cls,
        goal_state: Any,
        indicator_id: str,
    ) -> Any:
        """
        Backward-compatible alias.
        """

        return cls._resolve_indicator(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

    # ==========================================================
    # Evaluation Identity
    # ==========================================================

    @staticmethod
    def _validate_turn_identity(
        *,
        evidence: Any,
        turn_index: int | None,
    ) -> None:
        """Validate that committed evidence belongs to this turn."""

        if turn_index is None:
            return

        if isinstance(turn_index, bool) or not isinstance(turn_index, int):
            raise ValueError("turn_index must be an integer.")

        evidence_turn_index = getattr(evidence, "turn_index", None)

        if evidence_turn_index is None:
            raise ValueError(
                "Evaluator evidence must expose turn_index for a learner evaluation."
            )

        if evidence_turn_index != turn_index:
            raise ValueError(
                "Evaluator evidence turn mismatch: "
                f"expected '{turn_index}', received '{evidence_turn_index}'."
            )

        evidence_question = getattr(evidence, "question", None)
        if not isinstance(evidence_question, str) or not evidence_question.strip():
            raise ValueError(
                "Evaluator evidence must expose question for a learner evaluation."
            )

        evidence_answer = getattr(evidence, "answer", None)
        if not isinstance(evidence_answer, str) or not evidence_answer.strip():
            raise ValueError(
                "Evaluator evidence must expose answer for a learner evaluation."
            )

    # ==========================================================
    # Evidence Application
    # ==========================================================

    @classmethod
    def _validated_evidence_values(
        cls,
        *,
        evidence: Any,
    ) -> dict[str, Any]:
        """
        Extract and normalize all values before state mutation.
        """

        return {
            "achievement_level": (
                cls._normalize_achievement_level(
                    getattr(
                        evidence,
                        "achievement_level",
                        None,
                    )
                )
            ),
            "confidence": (
                cls._normalize_probability(
                    getattr(
                        evidence,
                        "confidence",
                        None,
                    ),
                    field_name="confidence",
                )
            ),
            "evidence_strength": (
                cls._normalize_probability(
                    getattr(
                        evidence,
                        "evidence_strength",
                        None,
                    ),
                    field_name="evidence_strength",
                )
            ),
            "demonstrated": (
                cls._normalize_demonstrated(
                    getattr(
                        evidence,
                        "indicator_demonstrated",
                        None,
                    )
                )
            ),
            "feedback": (
                cls._normalize_feedback(
                    getattr(
                        evidence,
                        "feedback",
                        None,
                    )
                )
            ),
        }

    @staticmethod
    def _apply_indicator_values(
        *,
        indicator: Any,
        values: dict[str, Any],
    ) -> None:
        """
        Apply one already-validated set of indicator values.

        Values are intentionally prepared before this method is called.
        """

        for field_name, value in values.items():
            try:
                setattr(
                    indicator,
                    field_name,
                    value,
                )
            except (
                AttributeError,
                TypeError,
            ) as exc:
                raise RuntimeError(
                    "Unable to update IndicatorState field "
                    f"'{field_name}'."
                ) from exc

    # ==========================================================
    # Evidence Storage
    # ==========================================================

    @staticmethod
    def _store_evidence(
        *,
        goal_state: Any,
        evidence: Any,
    ) -> None:
        add_evidence = getattr(
            goal_state,
            "add_evidence",
            None,
        )

        if not callable(add_evidence):
            raise TypeError(
                "GoalState must provide an add_evidence() method."
            )

        add_evidence(evidence)

    # ==========================================================
    # Evidence Validation
    # ==========================================================

    @classmethod
    def _validate_evidence(
        cls,
        *,
        evidence: Any,
        indicator_id: str,
    ) -> None:
        if evidence is None:
            raise ValueError(
                "Evaluator evidence is required."
            )

        cls._validate_evidence_indicator(
            evidence=evidence,
            indicator_id=indicator_id,
        )

        cls._validated_evidence_values(
            evidence=evidence,
        )

    @classmethod
    def _validate_evidence_indicator(
        cls,
        *,
        evidence: Any,
        indicator_id: str,
    ) -> None:
        evidence_indicator_id = (
            cls._extract_indicator_id(
                evidence
            )
        )

        normalized_indicator_id = (
            cls._normalize_indicator_id(
                indicator_id
            )
        )

        if (
            evidence_indicator_id
            != normalized_indicator_id
        ):
            raise ValueError(
                "Evaluator evidence indicator mismatch: "
                f"expected '{normalized_indicator_id}', "
                f"received '{evidence_indicator_id}'."
            )

    # ==========================================================
    # Indicator Helpers
    # ==========================================================

    @staticmethod
    def _extract_indicator_id(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        indicator_id = getattr(
            value,
            "id",
            None,
        )

        if indicator_id is None:
            indicator_id = getattr(
                value,
                "indicator_id",
                None,
            )

        if not isinstance(
            indicator_id,
            str,
        ):
            return None

        normalized = indicator_id.strip()

        return normalized or None

    # ==========================================================
    # GoalState Helpers
    # ==========================================================

    @staticmethod
    def _require_goal_state(
        goal_state: Any,
    ) -> None:
        if goal_state is None:
            raise ValueError(
                "OutcomeManager requires a GoalState."
            )

    # ==========================================================
    # Normalization
    # ==========================================================

    @staticmethod
    def _normalize_indicator_id(
        indicator_id: Any,
    ) -> str:
        if not isinstance(
            indicator_id,
            str,
        ):
            raise ValueError(
                "indicator_id must be a non-empty string."
            )

        normalized = indicator_id.strip()

        if not normalized:
            raise ValueError(
                "indicator_id must be a non-empty string."
            )

        return normalized

    @classmethod
    def _normalize_achievement_level(
        cls,
        value: Any,
    ) -> int:
        if isinstance(value, bool):
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
                "achievement_level must be finite."
            )

        if numeric != int(numeric):
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        normalized = int(numeric)

        if not (
            cls.MIN_ACHIEVEMENT_LEVEL
            <= normalized
            <= cls.MAX_ACHIEVEMENT_LEVEL
        ):
            raise ValueError(
                "achievement_level must be between "
                f"{cls.MIN_ACHIEVEMENT_LEVEL} and "
                f"{cls.MAX_ACHIEVEMENT_LEVEL}."
            )

        return normalized

    @classmethod
    def _normalize_probability(
        cls,
        value: Any,
        *,
        field_name: str,
    ) -> float:
        if isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be numeric."
            )

        try:
            normalized = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"{field_name} must be numeric."
            ) from exc

        if not math.isfinite(normalized):
            raise ValueError(
                f"{field_name} must be finite."
            )

        if not (
            cls.MIN_PROBABILITY
            <= normalized
            <= cls.MAX_PROBABILITY
        ):
            raise ValueError(
                f"{field_name} must be between "
                f"{cls.MIN_PROBABILITY} and "
                f"{cls.MAX_PROBABILITY}."
            )

        return normalized

    @staticmethod
    def _normalize_demonstrated(
        value: Any,
    ) -> bool:
        if not isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "indicator_demonstrated must be a boolean."
            )

        return value

    @staticmethod
    def _normalize_feedback(
        value: Any,
    ) -> str:
        if not isinstance(
            value,
            str,
        ):
            raise ValueError(
                "feedback must be a non-empty string."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "feedback must be a non-empty string."
            )

        return normalized

    @staticmethod
    def _normalize_attempts(
        value: Any,
    ) -> int:
        if isinstance(value, bool):
            raise ValueError(
                "Indicator attempts must be a non-negative integer."
            )

        try:
            numeric = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Indicator attempts must be a non-negative integer."
            ) from exc

        if not math.isfinite(numeric):
            raise ValueError(
                "Indicator attempts must be finite."
            )

        if numeric != int(numeric):
            raise ValueError(
                "Indicator attempts must be a non-negative integer."
            )

        normalized = int(numeric)

        if normalized < 0:
            raise ValueError(
                "Indicator attempts cannot be negative."
            )

        return normalized