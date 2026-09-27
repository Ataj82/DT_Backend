"""
app/assessment/engine.py

Runtime-facing assessment coordinator.

AssessmentEngine coordinates exactly one learner-answer evaluation
step and protects the evaluation boundary from runtime navigation
changes.

Responsibilities
----------------
- Validate runtime context.
- Resolve the goal belonging to the answered turn.
- Resolve the indicator belonging to the answered turn.
- Validate goal identity when supplied.
- Validate indicator ownership.
- Validate the answered-turn identity.
- Validate the question belongs to the answered turn.
- Record the learner answer in AssessmentContext.
- Delegate evaluation to EvaluationService.
- Validate the returned GoalDecision.

Non-responsibilities
--------------------
- Evaluating learner answers.
- Calculating assessment metrics.
- Mutating GoalState directly.
- Storing assessment evidence.
- Calculating coverage.
- Calculating mastery.
- Calculating confidence.
- Selecting the next indicator.
- Navigating between goals.
- Deciding goal completion independently.

Architecture
------------
    Answered Turn
          ↓
    AssessmentEngine
          ↓
    EvaluationService
          ↓
    OutcomeManager
          ↓
    CoverageEngine
          ↓
    ProgressReasoner
          ↓
    GoalDecision
          ↓
    Conversation / Navigation layer
"""

from __future__ import annotations

from typing import Any

from .decision import DecisionStatus, GoalDecision
from .evaluation_context import EvaluationContext


class AssessmentEngine:
    """
    Thin application-layer assessment coordinator.

    The engine is deliberately strict about evaluation identity.

    An answer must be evaluated against the same goal and indicator
    that produced the answered turn. The question supplied for
    evaluation must also belong to that answered turn.

    IMPORTANT
    ---------
    AssessmentContext.current_* represents the runtime navigation
    position. That position may already have advanced to the next
    question by the time evaluation occurs.

    Therefore, when an EvaluationContext is supplied, it is the
    authoritative identity of the answered turn.
    """

    def __init__(
        self,
        *,
        evaluation_service: Any,
    ) -> None:
        if evaluation_service is None:
            raise ValueError(
                "AssessmentEngine requires an evaluation_service."
            )

        evaluate = getattr(
            evaluation_service,
            "evaluate",
            None,
        )

        if not callable(evaluate):
            raise TypeError(
                "AssessmentEngine requires an evaluation_service "
                "with a callable evaluate() method."
            )

        self.evaluation_service = evaluation_service

    # ==========================================================
    # Public API
    # ==========================================================

    def evaluate(
        self,
        context: Any,
        answer: str,
        *,
        question: str | None = None,
        indicator_id: str | None = None,
        goal_id: str | None = None,
        turn_index: int | None = None,
        evaluation_context: EvaluationContext | None = None,
    ) -> GoalDecision:
        """
        Evaluate exactly the captured answered turn.

        ``evaluation_context`` is the preferred API. The legacy scalar
        arguments remain supported so existing callers do not break.

        When ``evaluation_context`` is supplied:

        - its goal_id identifies the GoalState to evaluate;
        - its indicator_id identifies the indicator;
        - its question identifies the answered question;
        - its answer is the learner answer;
        - its turn_index identifies the conversation turn.

        Navigation state is never used to reinterpret those fields.
        """

        self._validate_context(context)

        # ------------------------------------------------------
        # Build the immutable evaluation identity when a legacy
        # caller has not supplied one.
        # ------------------------------------------------------

        if evaluation_context is None:
            normalized_answer = self._normalize_answer(answer)

            normalized_question = self._normalize_question(
                question
            )

            resolved_indicator_id = (
                self._normalize_identifier(
                    indicator_id
                )
            )

            resolved_goal_id = (
                self._normalize_identifier(
                    goal_id
                )
            )

            if resolved_goal_id is None:
                resolved_goal_id = (
                    self._normalize_identifier(
                        getattr(
                            context,
                            "current_goal_id",
                            None,
                        )
                    )
                )

            if resolved_indicator_id is None:
                resolved_indicator_id = (
                    self._normalize_identifier(
                        getattr(
                            context,
                            "current_indicator_id",
                            None,
                        )
                    )
                )

            if not normalized_question:
                normalized_question = (
                    self._normalize_question(
                        getattr(
                            context,
                            "current_question",
                            None,
                        )
                    )
                )

            if (
                resolved_goal_id is None
                or resolved_indicator_id is None
            ):
                raise ValueError(
                    "Evaluation requires goal_id and indicator_id "
                    "for the answered turn."
                )

            if not normalized_question:
                raise ValueError(
                    "Evaluation requires the question belonging "
                    "to the answered turn."
                )

            resolved_turn_index = turn_index

            if resolved_turn_index is None:
                resolved_turn_index = (
                    self._current_turn_index(
                        context
                    )
                )

            if resolved_turn_index is None:
                raise ValueError(
                    "Evaluation requires turn_index for "
                    "the answered turn."
                )

            evaluation_context = EvaluationContext(
                turn_index=resolved_turn_index,
                goal_id=resolved_goal_id,
                indicator_id=resolved_indicator_id,
                question=normalized_question,
                answer=normalized_answer,
            )

        elif not isinstance(
            evaluation_context,
            EvaluationContext,
        ):
            raise TypeError(
                "evaluation_context must be an EvaluationContext."
            )

        # ------------------------------------------------------
        # CRITICAL STEP #1 BOUNDARY
        #
        # Validate against the actual answered turn, not the
        # mutable navigation state.
        # ------------------------------------------------------

        self._validate_captured_turn(
            context=context,
            evaluation_context=evaluation_context,
        )

        # From this point onward, evaluation identity is frozen.
        # Never substitute context.current_goal_id/current_indicator_id/current_question.

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            raise RuntimeError(
                "AssessmentContext does not provide a session."
            )

        get_goal_state = getattr(
            session,
            "get_goal_state",
            None,
        )

        if not callable(get_goal_state):
            raise RuntimeError(
                "InterviewSession must provide get_goal_state()."
            )

        # ------------------------------------------------------
        # CRITICAL STEP #1 FIX
        #
        # Resolve GoalState by the goal belonging to the answered
        # turn. Do NOT resolve it from navigator.current_goal_state().
        #
        # The navigator is allowed to move forward independently.
        # ------------------------------------------------------

        goal_state = get_goal_state(
            evaluation_context.goal_id
        )

        if goal_state is None:
            return self._no_active_goal_decision(
                reason=(
                    "The goal belonging to the answered turn "
                    "is no longer available."
                )
            )

        # ------------------------------------------------------
        # Verify that the captured indicator belongs to the
        # captured goal.
        # ------------------------------------------------------

        self._validate_indicator(
            goal_state=goal_state,
            indicator_id=evaluation_context.indicator_id,
        )

        # ------------------------------------------------------
        # Record the answer exactly once at the assessment
        # boundary.
        # ------------------------------------------------------

        self._record_answer(
            context=context,
            answer=evaluation_context.answer,
        )

        # ------------------------------------------------------
        # Delegate semantic evaluation.
        #
        # EvaluationService receives only the captured turn
        # identity and therefore cannot infer the target from
        # the navigator's current position.
        # ------------------------------------------------------

        decision = self.evaluation_service.evaluate(
            goal_state=goal_state,
            indicator_id=evaluation_context.indicator_id,
            question=evaluation_context.question,
            answer=evaluation_context.answer,
            turn_index=evaluation_context.turn_index,
        )

        self._validate_decision(
            decision
        )

        return decision

    # ==========================================================
    # Captured Turn Identity
    # ==========================================================

    @classmethod
    def _validate_captured_turn(
        cls,
        *,
        context: Any,
        evaluation_context: EvaluationContext,
    ) -> None:
        """
        Validate the captured evaluation identity against the
        persisted answered turn.

        AssessmentContext.current_* fields are deliberately NOT
        used here.

        Those fields represent the runtime's current navigation
        position and may already have been synchronized to the
        next goal, indicator, or question.

        The persisted session.last_turn is authoritative for the
        turn currently being evaluated.
        """

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            raise RuntimeError(
                "AssessmentContext does not provide a session."
            )

        answered_turn = getattr(
            session,
            "last_turn",
            None,
        )

        if answered_turn is None:
            raise ValueError(
                "Assessment turn validation requires "
                "a persisted last turn."
            )

        # ------------------------------------------------------
        # Turn index
        # ------------------------------------------------------

        answered_index = getattr(
            answered_turn,
            "index",
            None,
        )

        if (
            answered_index is not None
            and answered_index
            != evaluation_context.turn_index
        ):
            raise ValueError(
                "Assessment turn index mismatch: "
                f"the supplied evaluation context targets "
                f"turn {evaluation_context.turn_index}, "
                f"but the session last turn is "
                f"{answered_index}."
            )

        # ------------------------------------------------------
        # Goal identity
        # ------------------------------------------------------

        answered_goal_id = (
            cls._normalize_identifier(
                getattr(
                    answered_turn,
                    "goal_id",
                    None,
                )
            )
        )

        if (
            answered_goal_id is not None
            and answered_goal_id
            != evaluation_context.goal_id
        ):
            raise ValueError(
                "Assessment turn goal mismatch: "
                f"the answered turn belongs to "
                f"'{answered_goal_id}', "
                f"but the evaluation context targets "
                f"'{evaluation_context.goal_id}'."
            )

        # ------------------------------------------------------
        # Indicator identity
        # ------------------------------------------------------

        answered_indicator_id = (
            cls._normalize_identifier(
                getattr(
                    answered_turn,
                    "indicator_id",
                    None,
                )
            )
        )

        if (
            answered_indicator_id is not None
            and answered_indicator_id
            != evaluation_context.indicator_id
        ):
            raise ValueError(
                "Assessment turn indicator mismatch: "
                f"the answered turn belongs to "
                f"'{answered_indicator_id}', "
                f"but the evaluation context targets "
                f"'{evaluation_context.indicator_id}'."
            )

        # ------------------------------------------------------
        # Question identity
        # ------------------------------------------------------

        answered_question = (
            cls._normalize_question(
                getattr(
                    answered_turn,
                    "question",
                    None,
                )
            )
        )

        if (
            answered_question
            and answered_question
            != evaluation_context.question
        ):
            raise ValueError(
                "Assessment question mismatch: "
                "the evaluation context question does not "
                "match the persisted answered turn."
            )

    # ==========================================================
    # Legacy Turn Identity Compatibility
    # ==========================================================

    @classmethod
    def _validate_turn_identity(
        cls,
        *,
        context: Any,
        goal_id: str | None,
        indicator_id: str | None,
        question: str,
        turn_index: int | None,
    ) -> None:
        """
        Validate evaluation identity against the persisted answered
        conversation turn.

        This method is retained for compatibility with existing
        callers.

        IMPORTANT
        ---------
        It intentionally does NOT compare against:

            context.current_goal_id
            context.current_indicator_id
            context.current_question

        Those values describe navigation state, not historical
        answered-turn identity.
        """

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            raise RuntimeError(
                "AssessmentContext does not provide a session."
            )

        answered_turn = getattr(
            session,
            "last_turn",
            None,
        )

        if answered_turn is None:
            raise ValueError(
                "Assessment turn validation requires "
                "a persisted last turn."
            )

        answered_turn_index = getattr(
            answered_turn,
            "index",
            None,
        )

        if (
            turn_index is not None
            and answered_turn_index is not None
            and turn_index != answered_turn_index
        ):
            raise ValueError(
                "Assessment turn mismatch: "
                f"turn index is '{turn_index}', "
                f"but answered turn is "
                f"'{answered_turn_index}'."
            )

        answered_goal_id = (
            cls._normalize_identifier(
                getattr(
                    answered_turn,
                    "goal_id",
                    None,
                )
            )
        )

        normalized_goal_id = (
            cls._normalize_identifier(
                goal_id
            )
        )

        if (
            normalized_goal_id is not None
            and answered_goal_id is not None
            and normalized_goal_id
            != answered_goal_id
        ):
            raise ValueError(
                "Assessment turn goal mismatch: "
                f"turn goal is '{normalized_goal_id}', "
                f"but answered turn belongs to "
                f"'{answered_goal_id}'."
            )

        answered_indicator_id = (
            cls._normalize_identifier(
                getattr(
                    answered_turn,
                    "indicator_id",
                    None,
                )
            )
        )

        normalized_indicator_id = (
            cls._normalize_identifier(
                indicator_id
            )
        )

        if (
            normalized_indicator_id is not None
            and answered_indicator_id is not None
            and normalized_indicator_id
            != answered_indicator_id
        ):
            raise ValueError(
                "Assessment turn indicator mismatch: "
                f"turn indicator is "
                f"'{normalized_indicator_id}', "
                f"but answered turn belongs to "
                f"'{answered_indicator_id}'."
            )

        answered_question = (
            cls._normalize_question(
                getattr(
                    answered_turn,
                    "question",
                    None,
                )
            )
        )

        normalized_question = (
            cls._normalize_question(
                question
            )
        )

        if (
            normalized_question
            and answered_question
            and normalized_question
            != answered_question
        ):
            raise ValueError(
                "Assessment question mismatch: "
                "the question supplied for evaluation "
                "does not match the persisted answered "
                "conversation turn."
            )

    @staticmethod
    def _current_turn_index(
        context: Any,
    ) -> int | None:
        """
        Resolve the current conversation-turn index.

        InterviewSession.last_turn is the preferred source.
        """

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return None

        turn = getattr(
            session,
            "last_turn",
            None,
        )

        if turn is None:
            return None

        value = getattr(
            turn,
            "index",
            None,
        )

        if isinstance(
            value,
            int,
        ):
            return value

        return None

    # ==========================================================
    # Context
    # ==========================================================

    @staticmethod
    def _validate_context(
        context: Any,
    ) -> None:
        """
        Validate the runtime assessment context.
        """

        if context is None:
            raise ValueError(
                "AssessmentEngine requires an AssessmentContext."
            )

    @staticmethod
    def _resolve_navigator(
        context: Any,
    ) -> Any:
        """
        Resolve and validate the runtime navigator.

        This remains available for legacy callers and navigation
        compatibility. It is deliberately NOT used to resolve the
        GoalState when an EvaluationContext is available.
        """

        navigator = getattr(
            context,
            "navigator",
            None,
        )

        if navigator is None:
            raise RuntimeError(
                "AssessmentContext does not provide a navigator."
            )

        current_goal_state = getattr(
            navigator,
            "current_goal_state",
            None,
        )

        if not callable(
            current_goal_state
        ):
            raise RuntimeError(
                "Assessment navigator must provide "
                "current_goal_state()."
            )

        current_indicator = getattr(
            navigator,
            "current_indicator",
            None,
        )

        if not callable(
            current_indicator
        ):
            raise RuntimeError(
                "Assessment navigator must provide "
                "current_indicator()."
            )

        return navigator

    # ==========================================================
    # Goal Identity
    # ==========================================================

    @classmethod
    def _resolve_goal_id(
        cls,
        *,
        context: Any,
        goal_state: Any,
    ) -> str:
        """
        Resolve the canonical goal ID.

        GoalState is preferred because it is the assessment-domain
        state being evaluated.
        """

        goal_id = getattr(
            goal_state,
            "goal_id",
            None,
        )

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
            goal_id = getattr(
                context,
                "current_goal_id",
                None,
            )

        normalized = cls._normalize_identifier(
            goal_id
        )

        if normalized is None:
            raise RuntimeError(
                "Unable to resolve the active goal ID."
            )

        return normalized

    # ==========================================================
    # Question Compatibility
    # ==========================================================

    @staticmethod
    def _validate_question(
        *,
        context: Any,
        question: str,
    ) -> None:
        """
        Validate the question against the runtime's captured
        question.

        This method is retained for compatibility.

        New evaluation flow should use _validate_captured_turn()
        because AssessmentContext.current_question may already
        represent the next navigation question.
        """

        if not question:
            return

        current_question = getattr(
            context,
            "current_question",
            None,
        )

        if current_question is None:
            return

        if not isinstance(
            current_question,
            str,
        ):
            raise TypeError(
                "AssessmentContext.current_question must be a string."
            )

        normalized_current_question = (
            current_question.strip()
        )

        if (
            normalized_current_question
            and normalized_current_question
            != question
        ):
            raise ValueError(
                "Assessment question mismatch: "
                "the supplied question does not match "
                "AssessmentContext.current_question."
            )

    # ==========================================================
    # Normalization
    # ==========================================================

    @staticmethod
    def _normalize_answer(
        answer: Any,
    ) -> str:
        """
        Normalize the learner answer.
        """

        if answer is None:
            raise ValueError(
                "Interview answer cannot be empty."
            )

        if not isinstance(
            answer,
            str,
        ):
            raise TypeError(
                "Interview answer must be a string."
            )

        normalized = answer.strip()

        if not normalized:
            raise ValueError(
                "Interview answer cannot be empty."
            )

        return normalized

    @staticmethod
    def _normalize_question(
        question: Any,
    ) -> str:
        """
        Normalize an optional assessment question.
        """

        if question is None:
            return ""

        if not isinstance(
            question,
            str,
        ):
            raise TypeError(
                "Assessment question must be a string."
            )

        return question.strip()

    @staticmethod
    def _normalize_identifier(
        value: Any,
    ) -> str | None:
        """
        Normalize an optional identifier.

        Identifiers are not coerced from arbitrary objects because
        doing so can hide invalid runtime state.
        """

        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            raise TypeError(
                "Assessment identifier must be a string."
            )

        normalized = value.strip()

        return normalized or None

    # ==========================================================
    # Indicator Validation
    # ==========================================================

    @classmethod
    def _resolve_indicator_id(
        cls,
        *,
        context: Any,
        navigator: Any,
        indicator_id: str | None,
    ) -> str:
        """
        Resolve the indicator to evaluate.

        This legacy helper validates against the navigator's active
        indicator. The captured-turn evaluation path does not use
        it because the answered turn is authoritative.
        """

        current_indicator = navigator.current_indicator(
            context
        )

        if current_indicator is None:
            raise RuntimeError(
                "Cannot evaluate answer: "
                "no active indicator exists."
            )

        current_id = cls._extract_identifier(
            current_indicator
        )

        if current_id is None:
            raise RuntimeError(
                "Current indicator does not provide "
                "a valid ID."
            )

        if indicator_id is None:
            return current_id

        if indicator_id != current_id:
            raise ValueError(
                "Assessment indicator mismatch: "
                f"answer targets '{indicator_id}', "
                f"but active indicator is '{current_id}'."
            )

        return indicator_id

    @staticmethod
    def _validate_indicator(
        *,
        goal_state: Any,
        indicator_id: str,
    ) -> None:
        """
        Verify that the GoalState owns the captured indicator.
        """

        get_indicator = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(
            get_indicator
        ):
            indicator = get_indicator(
                indicator_id
            )

            if indicator is None:
                raise ValueError(
                    f"Unknown indicator '{indicator_id}'."
                )

            return

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if indicators is None:
            raise RuntimeError(
                "GoalState does not provide indicator access."
            )

        if isinstance(
            indicators,
            dict,
        ):
            if indicator_id not in indicators:
                raise ValueError(
                    f"Unknown indicator '{indicator_id}'."
                )

            return

        try:
            iterator = iter(
                indicators
            )
        except TypeError as exc:
            raise RuntimeError(
                "GoalState indicators must be a mapping or iterable."
            ) from exc

        for indicator in iterator:
            current_id = (
                AssessmentEngine._extract_identifier(
                    indicator
                )
            )

            if current_id == indicator_id:
                return

        raise ValueError(
            f"Unknown indicator '{indicator_id}'."
        )

    @classmethod
    def _validate_active_indicator(
        cls,
        *,
        context: Any,
        navigator: Any,
        indicator_id: str,
    ) -> None:
        """
        Ensure the requested indicator is the navigator's active
        indicator.

        Legacy compatibility helper. The captured-turn evaluation
        path deliberately does not use navigator state as the
        identity of the answered turn.
        """

        current_indicator = navigator.current_indicator(
            context
        )

        if current_indicator is None:
            raise RuntimeError(
                "Cannot evaluate answer: "
                "no active indicator exists."
            )

        current_id = cls._extract_identifier(
            current_indicator
        )

        if current_id is None:
            raise RuntimeError(
                "Active indicator does not provide "
                "a valid ID."
            )

        if current_id != indicator_id:
            raise ValueError(
                "Assessment indicator mismatch: "
                f"answer targets '{indicator_id}', "
                f"but active indicator is '{current_id}'."
            )

    @classmethod
    def _extract_identifier(
        cls,
        value: Any,
    ) -> str | None:
        """
        Extract an identifier from either a string or an object
        exposing ``id``.
        """

        if value is None:
            return None

        if isinstance(
            value,
            str,
        ):
            return cls._normalize_identifier(
                value
            )

        return cls._normalize_identifier(
            getattr(
                value,
                "id",
                None,
            )
        )

    # ==========================================================
    # Runtime Context
    # ==========================================================

    @staticmethod
    def _record_answer(
        *,
        context: Any,
        answer: str,
    ) -> None:
        """
        Record the learner answer in AssessmentContext.

        This method is the single assessment-boundary owner of
        runtime answer bookkeeping.

        AssessmentRuntime must not record the same answer again.
        """

        add_answer = getattr(
            context,
            "add_answer",
            None,
        )

        if not callable(
            add_answer
        ):
            raise RuntimeError(
                "AssessmentContext does not provide add_answer()."
            )

        add_answer(
            answer
        )

    # ==========================================================
    # Decision Validation
    # ==========================================================

    @staticmethod
    def _validate_decision(
        decision: Any,
    ) -> None:
        """
        Validate the canonical GoalDecision contract.
        """

        if not isinstance(
            decision,
            GoalDecision,
        ):
            raise TypeError(
                "EvaluationService must return GoalDecision; "
                f"received {type(decision).__name__}."
            )

        status = decision.status

        if not isinstance(
            status,
            str,
        ) or not status.strip():
            raise ValueError(
                "GoalDecision.status must be a non-empty string."
            )

        valid_statuses = (
            DecisionStatus.all_statuses()
        )

        if status not in valid_statuses:
            raise ValueError(
                "GoalDecision contains an unknown "
                f"assessment status '{status}'."
            )

        if status == DecisionStatus.COMPLETE:
            if decision.next_indicator is not None:
                raise ValueError(
                    "A COMPLETE GoalDecision cannot contain "
                    "a next_indicator."
                )

        elif status == DecisionStatus.FAILED:
            if decision.next_indicator is not None:
                raise ValueError(
                    "A FAILED GoalDecision cannot contain "
                    "a next_indicator."
                )

    # ==========================================================
    # No Active Goal
    # ==========================================================

    @staticmethod
    def _no_active_goal_decision(
        reason: str = "No active goal remains for assessment.",
    ) -> GoalDecision:
        """
        Handle an absent goal without inventing a new
        DecisionStatus.
        """

        return GoalDecision(
            status=DecisionStatus.FAILED,
            reason=reason,
            next_indicator=None,
            coverage=0.0,
            mastery=0.0,
            confidence=0.0,
        )