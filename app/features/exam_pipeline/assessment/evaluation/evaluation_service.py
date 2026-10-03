"""
app/assessment/evaluation/evaluation_service.py

Canonical application service for exactly one assessment turn.

Architecture
------------

    GoalState
        |
        v
    indicator validation
        |
        v
    AnswerEvaluator
        |
        v
    AnswerEvidence
        |
        v
    OutcomeManager
        |
        v
    CoverageEngine
        |
        +---- completed ----> COMPLETE
        |
        v
    ProgressReasoner
        |
        v
    GoalDecision

EvaluationService owns orchestration only.

It does not:
- generate questions
- select interview indicators
- calculate mastery
- calculate coverage
- calculate confidence
- mutate GoalState directly
- decide completion independently of CoverageEngine
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from typing import Any, Optional

from ..decision import (
    DecisionStatus,
    GoalDecision,
)


class EvaluationService:
    """
    Coordinate exactly one learner-answer evaluation.

    CoverageEngine is the sole source of canonical goal completion
    and aggregate assessment metrics.
    """

    MIN_ACHIEVEMENT_LEVEL = 1
    MAX_ACHIEVEMENT_LEVEL = 6

    MIN_PROBABILITY = 0.0
    MAX_PROBABILITY = 1.0

    def __init__(
        self,
        *,
        evaluator: Any,
        outcome_manager: Any,
        progress_reasoner: Any,
        coverage_engine: Any,
    ) -> None:
        self.evaluator = self._require_dependency(
            evaluator,
            "evaluator",
        )

        self.outcome_manager = self._require_dependency(
            outcome_manager,
            "outcome_manager",
        )

        self.progress_reasoner = self._require_dependency(
            progress_reasoner,
            "progress_reasoner",
        )

        self.coverage_engine = self._require_dependency(
            coverage_engine,
            "coverage_engine",
        )

    # ==========================================================
    # Public API
    # ==========================================================

    def evaluate(
        self,
        *,
        goal_state: Any,
        indicator_id: str,
        question: str,
        answer: str,
        turn_index: int | None = None,
        assessment_target: dict[str, Any] | None = None,
        language: str = "en",
    ) -> GoalDecision:
        """
        Evaluate exactly one learner answer.

        One call produces:
            one evaluator invocation
            one OutcomeManager mutation
            one canonical CoverageEngine snapshot
        """

        if goal_state is None:
            return GoalDecision(
                status=DecisionStatus.FAILED,
                reason="No goal state is available.",
            )

        normalized_indicator_id = (
            self._normalize_indicator_id(
                indicator_id
            )
        )

        self._require_indicator(
            goal_state,
            normalized_indicator_id,
        )

        normalized_question = (
            self._normalize_question(question)
        )

        normalized_answer = (
            self._normalize_answer(answer)
        )

        evidence = self._evaluate_answer(
            goal_state=goal_state,
            indicator_id=normalized_indicator_id,
            question=normalized_question,
            answer=normalized_answer,
            turn_index=turn_index,
            assessment_target=assessment_target,
            language=language,
        )

        evidence = self._attach_evaluation_identity(
            evidence,
            turn_index=turn_index,
            question=normalized_question,
            answer=normalized_answer,
        )

        if turn_index is not None and getattr(evidence, "turn_index", None) != turn_index:
            raise ValueError(
                "Evaluator evidence turn_index does not match the evaluated turn."
            )

        if str(getattr(evidence, "question", "") or "").strip() != normalized_question:
            raise ValueError(
                "Evaluator evidence question does not match the evaluated question."
            )

        if str(getattr(evidence, "answer", "") or "").strip() != normalized_answer:
            raise ValueError(
                "Evaluator evidence answer does not match the evaluated answer."
            )

        expected_fingerprint = self._request_fingerprint(
            turn_index=turn_index,
            question=normalized_question,
            answer=normalized_answer,
        )
        actual_fingerprint = str(
            getattr(evidence, "request_fingerprint", "") or ""
        ).strip()
        if actual_fingerprint != expected_fingerprint:
            raise ValueError(
                "Evaluator evidence request_fingerprint does not match "
                "the evaluated turn."
            )

        indicator = self._require_indicator(
            goal_state,
            normalized_indicator_id,
        )
        before_attempts = self._attempt_count(indicator)

        self.outcome_manager.apply_evaluation(
            goal_state,
            indicator_id=normalized_indicator_id,
            evidence=evidence,
            turn_index=turn_index,
        )

        after_attempts = self._attempt_count(indicator)

        if after_attempts != before_attempts + 1:
            raise RuntimeError(
                "Assessment state commit failed: "
                f"indicator '{normalized_indicator_id}' attempts changed "
                f"from {before_attempts} to {after_attempts}; expected "
                f"{before_attempts + 1}."
            )

        snapshot = self.coverage_engine.snapshot(
            goal_state
        )

        if snapshot is None:
            raise RuntimeError(
                "CoverageEngine returned no snapshot."
            )

        if snapshot.completed:
            return GoalDecision(
                status=DecisionStatus.COMPLETE,
                reason=(
                    "Assessment requirements are satisfied."
                ),
                next_indicator=None,
                coverage=snapshot.coverage,
                mastery=snapshot.mastery,
                confidence=snapshot.confidence,
            )

        decision = self.progress_reasoner.evaluate(
            goal_state
        )

        if decision is None:
            raise RuntimeError(
                "ProgressReasoner returned no GoalDecision."
            )

        # CoverageEngine owns completion.
        if decision.status == DecisionStatus.COMPLETE:
            return GoalDecision(
                status=DecisionStatus.CONTINUE,
                reason=(
                    "ProgressReasoner returned COMPLETE while "
                    "CoverageEngine reports the goal incomplete."
                ),
                next_indicator=decision.next_indicator,
                coverage=snapshot.coverage,
                mastery=snapshot.mastery,
                confidence=snapshot.confidence,
            )

        return GoalDecision(
            status=decision.status,
            reason=decision.reason,
            next_indicator=decision.next_indicator,
            coverage=snapshot.coverage,
            mastery=snapshot.mastery,
            confidence=snapshot.confidence,
        )

    @staticmethod
    def _request_fingerprint(
        *,
        turn_index: int | None,
        question: str,
        answer: str,
    ) -> str:
        """Recompute the canonical identity independently at the commit boundary."""
        payload = (
            f"{turn_index}|"
            f"{question.strip()}|"
            f"{answer.strip()}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def snapshot(
        self,
        goal_state: Any,
    ) -> Any:
        if goal_state is None:
            return None

        return self.coverage_engine.snapshot(
            goal_state
        )

    def completed(
        self,
        goal_state: Any,
    ) -> bool:
        if goal_state is None:
            return False

        return bool(
            self.coverage_engine.is_complete(
                goal_state
            )
        )

    # ==========================================================
    # Evaluation
    # ==========================================================

    def _evaluate_answer(
        self,
        *,
        goal_state: Any,
        indicator_id: str,
        question: str,
        answer: str,
        turn_index: Optional[int] = None,
        assessment_target: dict[str, Any] | None = None,
        language: str = "en",
    ) -> Any:
        evaluate = getattr(
            self.evaluator,
            "evaluate",
            None,
        )

        if not callable(evaluate):
            raise TypeError(
                "Configured evaluator must provide evaluate()."
            )

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        if goal is None:
            raise ValueError(
                "GoalState must expose its goal "
                "for answer evaluation."
            )

        try:
            evidence = evaluate(
                goal=goal,
                indicator_id=indicator_id,
                question=question,
                answer=answer,
                turn_index=turn_index,
                assessment_target=assessment_target,
                language=language,
            )
        except Exception as exc:
            # Preserve a safe, actionable reason while avoiding learner-answer
            # contents or provider internals in the public exception message.
            reason = str(exc).strip() or exc.__class__.__name__
            raise RuntimeError(
                f"Answer evaluation failed: {reason}"
            ) from exc

        return self._normalize_evidence(
            evidence,
            expected_indicator_id=indicator_id,
        )

    # ==========================================================
    # Evidence
    # ==========================================================

    @classmethod
    def _normalize_evidence(
        cls,
        evidence: Any,
        *,
        expected_indicator_id: str,
    ) -> Any:
        if evidence is None:
            raise ValueError(
                "Answer evaluator returned no evidence."
            )

        evidence_indicator_id = (
            getattr(
                evidence,
                "indicator_id",
                None,
            )
        )

        if evidence_indicator_id is None:
            raise ValueError(
                "Answer evaluator evidence must expose "
                "'indicator_id'."
            )

        normalized_evidence_indicator_id = (
            cls._normalize_indicator_id(
                evidence_indicator_id
            )
        )

        if (
            normalized_evidence_indicator_id
            != expected_indicator_id
        ):
            raise ValueError(
                "Answer evaluator returned evidence for "
                f"indicator '{normalized_evidence_indicator_id}', "
                f"but '{expected_indicator_id}' was requested."
            )

        achievement_level = getattr(
            evidence,
            "achievement_level",
            None,
        )

        if achievement_level is None:
            achievement_level = getattr(
                evidence,
                "achieved_level",
                None,
            )

        achievement_level = (
            cls._normalize_achievement_level(
                achievement_level
            )
        )

        confidence = cls._normalize_probability(
            getattr(
                evidence,
                "confidence",
                None,
            ),
            "confidence",
        )

        evidence_strength = cls._normalize_probability(
            getattr(
                evidence,
                "evidence_strength",
                None,
            ),
            "evidence_strength",
        )

        demonstrated = getattr(
            evidence,
            "indicator_demonstrated",
            None,
        )

        if not isinstance(
            demonstrated,
            bool,
        ):
            raise ValueError(
                "Evaluator evidence field "
                "'indicator_demonstrated' must be boolean."
            )

        feedback = getattr(
            evidence,
            "feedback",
            None,
        )

        if not isinstance(
            feedback,
            str,
        ):
            raise ValueError(
                "Evaluator evidence field "
                "'feedback' must be a string."
            )

        feedback = feedback.strip()

        if not feedback:
            raise ValueError(
                "Evaluator evidence field "
                "'feedback' must not be empty."
            )

        return cls._canonicalize_evidence(
            evidence=evidence,
            indicator_id=expected_indicator_id,
            achievement_level=achievement_level,
            confidence=confidence,
            evidence_strength=evidence_strength,
            indicator_demonstrated=demonstrated,
            feedback=feedback,
        )

    @classmethod
    def _canonicalize_evidence(
        cls,
        *,
        evidence: Any,
        indicator_id: str,
        achievement_level: int,
        confidence: float,
        evidence_strength: float,
        indicator_demonstrated: bool,
        feedback: str,
    ) -> Any:
        values = {
            "indicator_id": indicator_id,
            "achievement_level": achievement_level,
            "confidence": confidence,
            "evidence_strength": evidence_strength,
            "indicator_demonstrated": indicator_demonstrated,
            "feedback": feedback,
        }

        # ------------------------------------------------------
        # Dataclass path
        # ------------------------------------------------------

        try:
            canonical = replace(
                evidence,
                **values,
            )

            # Verify the replacement actually produced the
            # expected canonical attributes.
            for name, expected in values.items():
                actual = getattr(
                    canonical,
                    name,
                    None,
                )

                if actual != expected:
                    raise ValueError(
                        f"Canonical evidence field '{name}' "
                        "could not be normalized."
                    )

            return canonical

        except (
            TypeError,
            ValueError,
        ):
            pass

        # ------------------------------------------------------
        # Mutable legacy object path
        # ------------------------------------------------------

        for name, value in values.items():
            try:
                setattr(
                    evidence,
                    name,
                    value,
                )
            except (
                AttributeError,
                TypeError,
            ) as exc:
                raise ValueError(
                    "Evaluator evidence cannot be converted "
                    "to the canonical evidence contract."
                ) from exc

        return evidence

    @staticmethod
    def _attach_evaluation_identity(
        evidence: Any,
        *,
        turn_index: int | None,
        question: str,
        answer: str = "",
    ) -> Any:
        """Attach historical turn identity without breaking legacy evidence."""

        values: dict[str, Any] = {"question": question, "answer": answer}
        if turn_index is not None:
            values["turn_index"] = turn_index

        for name, value in values.items():
            if not hasattr(evidence, name):
                continue
            try:
                setattr(evidence, name, value)
            except (AttributeError, TypeError):
                try:
                    evidence = replace(evidence, **{name: value})
                except (TypeError, ValueError):
                    pass
        return evidence

    @staticmethod
    def _attempt_count(indicator: Any) -> int:
        value = getattr(indicator, "attempts", 0)
        if isinstance(value, bool):
            raise ValueError("Indicator attempts must be a non-negative integer.")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Indicator attempts must be a non-negative integer."
            ) from exc
        if not math.isfinite(numeric) or numeric != int(numeric) or numeric < 0:
            raise ValueError(
                "Indicator attempts must be a non-negative integer."
            )
        return int(numeric)

    # ==========================================================
    # Indicator Validation
    # ==========================================================

    @classmethod
    def _require_indicator(
        cls,
        goal_state: Any,
        indicator_id: str,
    ) -> Any:
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

        if isinstance(
            indicators,
            dict,
        ):
            indicator = indicators.get(
                normalized_indicator_id
            )

            if indicator is not None:
                return indicator

        if isinstance(
            indicators,
            (list, tuple),
        ):
            for candidate in indicators:
                candidate_id = (
                    getattr(
                        candidate,
                        "id",
                        None,
                    )
                    or getattr(
                        candidate,
                        "indicator_id",
                        None,
                    )
                )

                if candidate_id is None:
                    continue

                if (
                    cls._normalize_indicator_id(
                        candidate_id
                    )
                    == normalized_indicator_id
                ):
                    return candidate

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

    # ==========================================================
    # Normalization
    # ==========================================================

    @classmethod
    def _normalize_achievement_level(
        cls,
        value: Any,
    ) -> int:
        if value is None:
            raise ValueError(
                "achievement_level is required."
            )

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "achievement_level must be numeric."
            )

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "achievement_level must be numeric."
            ) from exc

        if not math.isfinite(number):
            raise ValueError(
                "achievement_level must be finite."
            )

        if number != int(number):
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        normalized = int(number)

        if not (
            cls.MIN_ACHIEVEMENT_LEVEL
            <= normalized
            <= cls.MAX_ACHIEVEMENT_LEVEL
        ):
            raise ValueError(
                "achievement_level must be between 1 and 6."
            )

        return normalized

    @classmethod
    def _normalize_probability(
        cls,
        value: Any,
        name: str,
    ) -> float:
        if value is None:
            raise ValueError(
                f"{name} is required."
            )

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                f"{name} must be numeric."
            )

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"{name} must be numeric."
            ) from exc

        if not math.isfinite(number):
            raise ValueError(
                f"{name} must be finite."
            )

        if not (
            cls.MIN_PROBABILITY
            <= number
            <= cls.MAX_PROBABILITY
        ):
            raise ValueError(
                f"{name} must be between 0.0 and 1.0."
            )

        return number

    @staticmethod
    def _normalize_indicator_id(
        indicator_id: Any,
    ) -> str:
        if indicator_id is None:
            raise ValueError(
                "indicator_id is required."
            )

        value = str(
            indicator_id
        ).strip()

        if not value:
            raise ValueError(
                "indicator_id is required."
            )

        return value

    @staticmethod
    def _normalize_answer(
        answer: Any,
    ) -> str:
        value = str(
            answer or ""
        ).strip()

        if not value:
            raise ValueError(
                "Interview answer cannot be empty."
            )

        return value

    @staticmethod
    def _normalize_question(
        question: Any,
    ) -> str:
        return str(
            question or ""
        ).strip()

    @staticmethod
    def _require_dependency(
        dependency: Any,
        name: str,
    ) -> Any:
        if dependency is None:
            raise ValueError(
                f"EvaluationService requires a {name}."
            )

        return dependency