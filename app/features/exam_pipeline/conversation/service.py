"""
app/conversation/service.py

Conversation orchestration for one assessment interview.

ConversationService coordinates one conversational step at a time.

Responsibilities
----------------
- Create interviewer questions.
- Process learner answers.
- Delegate evaluation to the canonical EvaluationService.
- Preserve evaluation feedback.
- Ask InterviewNavigator for progression.
- Delegate question generation.
- Prevent duplicate questions.
- Advance goals.
- Mark the interview complete.

Non-responsibilities
--------------------
- Persistence.
- Transactions.
- Answer evaluation.
- Assessment metric calculation.
- Question generation.
- Goal navigation algorithms.
- Report construction.

Turn identity invariant
-----------------------
Every assessable ConversationTurn must preserve:

    turn.index
    turn.goal_id
    turn.indicator_id
    turn.question

Before evaluation, ConversationService creates an immutable
EvaluationContext from those exact values.

Question generation invariant
-----------------------------
A GeneratedQuestion must:

    1. contain a non-empty question;
    2. contain a non-empty indicator_id;
    3. match the indicator requested by ConversationService.

The same indicator may legitimately receive different questions
across repeated attempts.

Terminal semantics
------------------
PASSED
    Successful academic completion.

FAILED / EXHAUSTED
    Terminal unsuccessful resolution.

resolved
    No further assessment should occur.

ConversationService applies the terminal goal decision before
asking InterviewNavigator to advance.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable
from typing import Any

from ..assessment.evaluation_context import EvaluationContext
from ..assessment.adaptive_decision_trace import AdaptiveDecisionTrace
from ..assessment.goal_time_manager import GoalTimeManager
from ..assessment.robust_goal_manager import GoalManager
from ..assessment.goal_evidence_continuity import (
    GoalEvidenceContinuityManager,
    QuestionContinuityError,
)
from ..assessment.difficulty import AdaptiveDifficultyController
from ..interview.conversation_turn import ConversationTurn
from ..interview.generated_question import GeneratedQuestion
from ..interview.question_request import QuestionRequest
from ..templates.models import InterviewTemplate


logger = logging.getLogger(__name__)


class DuplicateQuestionGenerationError(RuntimeError):
    """Question generation exhausted diversity retries without a new question."""


class QuestionDifficultyGenerationError(RuntimeError):
    """Question generation exhausted retries while violating difficulty target."""


class ConversationService:
    """
    Stateless conversational orchestration boundary.

    Runtime assessment state lives in AssessmentContext / GoalState.
    """

    COMPLETION_MESSAGE = "Interview complete."

    DEFAULT_TEMPLATE_ID = "default-interview-template"
    DEFAULT_TEMPLATE_NAME = "Default Interview"

    MAX_DUPLICATE_QUESTION_RETRIES = 3
    QUESTION_HISTORY_LIMIT = 10

    def __init__(
        self,
        *,
        navigator,
        question_generator,
        evaluation_service=None,
        difficulty_controller=None,
        abet_service=None,
        assessment_engine=None,
    ) -> None:
        self.navigator = self._require_dependency(
            navigator,
            "navigator",
        )

        self.question_generator = self._require_dependency(
            question_generator,
            "question_generator",
        )

        if evaluation_service is None:
            evaluation_service = assessment_engine
        self.evaluation_service = self._require_dependency(
            evaluation_service,
            "evaluation_service",
        )

        # Optional for backward compatibility with direct unit tests.
        self.difficulty_controller = (
            difficulty_controller
            if difficulty_controller is not None
            else AdaptiveDifficultyController()
        )

        # Optional additive ABET layer. When absent, v7.x behavior is unchanged.
        self.abet_service = abet_service

    # ==========================================================
    # Public API
    # ==========================================================

    def first_turn(
        self,
        context,
    ) -> ConversationTurn:
        """
        Create the first interviewer turn.
        """

        self._validate_context(context)

        session = context.session

        if self._session_completed(session):
            return self._complete_turn(
                session=session,
                index=1,
            )

        goal = self.navigator.current_goal(context)

        if goal is None:
            return self._complete_turn(
                session=session,
                index=1,
            )

        if self._goal_is_resolved(context):
            return self._advance_until_question(
                context=context,
                start_index=0,
            )

        indicator = self._select_indicator(
            context=context,
        )

        if indicator is None:
            return self._advance_until_question(
                context=context,
                start_index=0,
            )

        return self._build_question_turn(
            context=context,
            goal=goal,
            indicator=indicator,
            index=1,
            selection_source="initial_goal_selection",
        )

    def next_turn(
        self,
        *,
        context,
        answer: str,
        previous_turn: ConversationTurn,
    ) -> ConversationTurn:
        """
        Process one learner answer and produce the next interviewer turn.
        """

        self._validate_context(context)
        self._validate_previous_turn(previous_turn)

        # ------------------------------------------------------
        # 1. Record answer on the exact turn being answered.
        # ------------------------------------------------------

        previous_turn.record_answer(answer)
        normalized_answer = previous_turn.answer

        # ------------------------------------------------------
        # 2. Freeze the complete identity of the answered turn.
        #
        # This happens BEFORE any evaluation or navigation can
        # mutate runtime state.
        # ------------------------------------------------------

        evaluation_context = self._build_evaluation_context(
            previous_turn=previous_turn,
            answer=normalized_answer,
        )

        logger.info(
            "Evaluating answered turn: turn_index=%s goal_id=%s indicator_id=%s question=%r answer=%r",
            evaluation_context.turn_index,
            evaluation_context.goal_id,
            evaluation_context.indicator_id,
            evaluation_context.question,
            evaluation_context.answer,
        )

        session = context.session
        goal_time_manager = GoalTimeManager(session)
        goal_manager = GoalManager(session)
        goal_time_manager.ensure_goal_started(previous_turn.goal_id)


        if self._session_completed(session):
            return self._complete_turn(
                session=session,
                index=previous_turn.index + 1,
            )

        # ------------------------------------------------------
        # 3. Evaluate EXACTLY this turn.
        # ------------------------------------------------------

        decision = self._evaluate_answer(
            context=context,
            answer=normalized_answer,
            previous_turn=previous_turn,
            evaluation_context=evaluation_context,
        )

        logger.info(
            "Evaluation identity verified: turn_index=%s goal_id=%s indicator_id=%s question=%r answer=%r",
            evaluation_context.turn_index,
            evaluation_context.goal_id,
            evaluation_context.indicator_id,
            evaluation_context.question,
            evaluation_context.answer,
        )

        self._log_decision(
            context=context,
            decision=decision,
        )

        # ------------------------------------------------------
        # 4. Preserve the decision on the answered turn.
        # ------------------------------------------------------

        previous_turn.decision = decision

        self._record_evaluation_snapshot(
            context=context,
            previous_turn=previous_turn,
            decision=decision,
        )

        # ------------------------------------------------------
        # 5. Preserve feedback belonging to THIS answer.
        # ------------------------------------------------------

        self._record_feedback(
            context=context,
            previous_turn=previous_turn,
        )

        # ------------------------------------------------------
        # 5a. Goal-manager observation.
        #
        # This is the authoritative goal-level adaptive layer: every goal
        # gets at least four answered questions, strong/medium evidence
        # increases the next challenge, weak evidence decreases it, and
        # terminal decisions are gated until evidence is sufficiently
        # certain.
        # ------------------------------------------------------
        latest_evidence = self._latest_evidence_for_turn(
            context=context,
            turn=previous_turn,
        )
        if latest_evidence is not None:
            goal_state_for_manager = self._goal_state_for_turn(
                context=context,
                turn=previous_turn,
            )
            if goal_state_for_manager is not None:
                goal_manager.observe(goal_state_for_manager, latest_evidence)

        # ------------------------------------------------------
        # 5b. Time-forced interview boundary.
        #
        # The answer has already been evaluated and its evidence snapshot
        # committed. The deadline now becomes authoritative: do not spend
        # time generating another question once the budget is exhausted.
        # ------------------------------------------------------
        if self._time_expired(context):
            return self._finish_due_to_time(
                context=context,
                previous_turn=previous_turn,
            )

        # ------------------------------------------------------
        # 5c. Goal-specific time boundary. The answer is already evaluated,
        # then an exhausted goal is failed and its unused time (if any) is
        # returned to the remaining-goal allocation pool.
        # ------------------------------------------------------
        current_goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )
        if current_goal_state is not None and goal_time_manager.goal_expired(previous_turn.goal_id):
            mark_failed = getattr(current_goal_state, "mark_failed", None)
            if callable(mark_failed) and not getattr(current_goal_state, "resolved", False):
                mark_failed()
            goal_time_manager.finish_goal(previous_turn.goal_id, outcome="failed_time")
            return self._advance_after_goal(
                context=context,
                previous_turn=previous_turn,
            )

        # ------------------------------------------------------
        # 5b. ABET assessment-plan completion is authoritative when
        # an explicit plan is attached. This is additive: sessions
        # without an ABET plan retain the v7.x navigator behavior.
        # ------------------------------------------------------
        if self.abet_service is not None and not self._time_forced_enabled(context):
            abet_assessment = self.abet_service.assessment(session)
            if (
                abet_assessment.get("enabled")
                and abet_assessment.get("completed")
                and self.navigator.finished(context)
            ):
                # ABET attainment is an assessment criterion, not an
                # independent permission to terminate the conversation.
                return self._complete_turn(
                    session=session,
                    index=previous_turn.index + 1,
                )

        # ------------------------------------------------------
        # 6. Adapt difficulty for the NEXT question on this indicator.
        # ------------------------------------------------------

        self._adapt_difficulty(
            context=context,
            previous_turn=previous_turn,
        )

        # ------------------------------------------------------
        # 7. Terminal goal decision.
        # ------------------------------------------------------

        if self._is_terminal_decision(decision):
            # A goal cannot finish before the minimum four questions, and
            # it cannot finish while the latest evidence is still uncertain.
            # When the gate blocks a terminal decision, deliberately probe
            # the same indicator again so the next question follows the
            # goal-level difficulty direction.
            goal_state_for_manager = self._goal_state_for_turn(
                context=context,
                turn=previous_turn,
            )
            if goal_state_for_manager is not None and latest_evidence is not None:
                if not goal_manager.terminal_allowed(
                    goal_state_for_manager, decision, latest_evidence
                ):
                    forced_indicator = goal_manager.indicator_for_minimum(
                        goal_state_for_manager, previous_turn.indicator_id
                    )
                    if forced_indicator is not None:
                        return self._build_question_turn(
                            context=context,
                            goal=goal_state_for_manager.goal,
                            indicator=forced_indicator,
                            index=previous_turn.index + 1,
                            excluded_questions=[previous_turn.question],
                            selection_source="goal_manager_minimum_or_certainty_probe",
                        )
            return self._advance_after_goal(
                context=context,
                previous_turn=previous_turn,
            )

        # ------------------------------------------------------
        # 7. Current goal still active.
        # ------------------------------------------------------

        goal = self.navigator.current_goal(context)

        if goal is None:
            if self.navigator.finished(context):
                return self._finish_previous_turn(
                    context=context,
                    previous_turn=previous_turn,
                )

            return self._advance_until_question(
                context=context,
                start_index=previous_turn.index,
                excluded_questions=[previous_turn.question],
            )

        if self._goal_is_resolved(context):
            return self._advance_after_goal(
                context=context,
                previous_turn=previous_turn,
            )

        preferred = self._preferred_indicator(decision)

        # A remediation decision means the current goal is intentionally
        # NOT resolved.  Do not send it back through the ordinary evidence
        # selector: that selector correctly stops once confidence/evidence
        # are strong, even when mastery is still below the target.  In that
        # case the remediation planner must explicitly select the same
        # indicator again. The interview deadline, not attempt count, is the hard boundary.
        if self._decision_status(decision) in {"remediate", "remediation", "retry", "probe"}:
            indicator = self._select_remediation_indicator(
                context=context,
                preferred=preferred,
            )
        else:
            indicator = self._select_indicator(
                context=context,
                preferred=preferred,
            )

        if indicator is None:
            return self._advance_after_goal(
                context=context,
                previous_turn=previous_turn,
            )

        return self._build_question_turn(
            context=context,
            goal=goal,
            indicator=indicator,
            index=previous_turn.index + 1,
            excluded_questions=[previous_turn.question],
            selection_source=(
                "remediation_selection"
                if self._decision_status(decision) in {"remediate", "remediation", "retry", "probe"}
                else "coverage_optimized_selection"
            ),
        )

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _validate_context(context) -> None:
        if context is None:
            raise ValueError(
                "ConversationService requires an AssessmentContext."
            )

        if getattr(context, "session", None) is None:
            raise ValueError(
                "AssessmentContext requires a session."
            )

    @staticmethod
    def _validate_previous_turn(
        previous_turn: ConversationTurn,
    ) -> None:
        if previous_turn is None:
            raise ValueError(
                "previous_turn is required."
            )

        if not isinstance(previous_turn, ConversationTurn):
            raise TypeError(
                "previous_turn must be a ConversationTurn."
            )

        if not isinstance(
            getattr(previous_turn, "index", None),
            int,
        ):
            raise TypeError(
                "previous_turn.index must be an integer."
            )

        question = getattr(
            previous_turn,
            "question",
            None,
        )

        if not isinstance(question, str) or not question.strip():
            raise ValueError(
                "previous_turn.question must be a non-empty string."
            )

    # ==========================================================
    # Dependency
    # ==========================================================

    @staticmethod
    def _require_dependency(
        dependency: Any,
        name: str,
    ) -> Any:
        if dependency is None:
            raise ValueError(
                f"ConversationService requires a {name}."
            )

        return dependency

    # ==========================================================
    # Logging
    # ==========================================================

    @staticmethod
    def _log_decision(
        *,
        context,
        decision,
    ) -> None:
        if decision is None:
            logger.warning(
                "EvaluationService returned no decision. "
                "current_goal=%s",
                getattr(
                    context,
                    "current_goal_id",
                    None,
                ),
            )
            return

        logger.info(
            (
                "Assessment decision: "
                "status=%s reason=%s next_indicator=%s "
                "coverage=%s mastery=%s confidence=%s "
                "current_goal=%s"
            ),
            getattr(
                decision,
                "status",
                None,
            ),
            getattr(
                decision,
                "reason",
                None,
            ),
            getattr(
                decision,
                "next_indicator",
                None,
            ),
            getattr(
                decision,
                "coverage",
                None,
            ),
            getattr(
                decision,
                "mastery",
                None,
            ),
            getattr(
                decision,
                "confidence",
                None,
            ),
            getattr(
                context,
                "current_goal_id",
                None,
            ),
        )

    # ==========================================================
    # Session
    # ==========================================================

    @staticmethod
    def _session_completed(session) -> bool:
        completed = getattr(
            session,
            "completed",
            False,
        )

        if callable(completed):
            completed = completed()

        return bool(completed)

    # ==========================================================
    # Assessment Identity
    # ==========================================================

    def _build_evaluation_context(
        self,
        *,
        previous_turn: ConversationTurn,
        answer: str,
    ) -> EvaluationContext:
        """
        Freeze the identity of the exact turn being evaluated.

        IMPORTANT:

        We intentionally read question / goal / indicator from
        previous_turn rather than from the current navigator state.

        The navigator may subsequently move to another goal or
        indicator. That must never change the identity of the answer
        that is currently being evaluated.
        """

        goal_id = str(
            getattr(
                previous_turn,
                "goal_id",
                "",
            )
            or ""
        ).strip()

        indicator_id = str(
            getattr(
                previous_turn,
                "indicator_id",
                "",
            )
            or ""
        ).strip()

        question = str(
            getattr(
                previous_turn,
                "question",
                "",
            )
            or ""
        ).strip()

        if not goal_id:
            raise RuntimeError(
                "Unable to evaluate answer: "
                "previous turn has no goal_id."
            )

        if not indicator_id:
            raise RuntimeError(
                "Unable to evaluate answer: "
                "previous turn has no indicator_id."
            )

        if not question:
            raise RuntimeError(
                "Unable to evaluate answer: "
                "previous turn has no question."
            )

        if not isinstance(answer, str):
            raise TypeError(
                "Unable to evaluate answer: "
                "answer must be a string."
            )

        return EvaluationContext(
            turn_index=previous_turn.index,
            goal_id=goal_id,
            indicator_id=indicator_id,
            question=question,
            answer=answer,
        )

    def _evaluate_answer(
        self,
        *,
        context,
        answer: str,
        previous_turn: ConversationTurn,
        evaluation_context: EvaluationContext,
    ):
        """
        Delegate answer evaluation to the canonical EvaluationService.

        EvaluationService owns the complete assessment pipeline.

        ConversationService supplies the immutable identity of the
        answered turn.
        """

        indicator_id = getattr(
            previous_turn,
            "indicator_id",
            None,
        )

        if not indicator_id:
            raise RuntimeError(
                "Unable to evaluate answer: "
                "previous turn has no indicator_id."
            )

        evaluate = getattr(
            self.evaluation_service,
            "evaluate",
            None,
        )

        if not callable(evaluate):
            raise TypeError(
                "Configured evaluation service must provide "
                "evaluate()."
            )

        normalized_indicator_id = str(
            indicator_id
        ).strip()

        if not normalized_indicator_id:
            raise RuntimeError(
                "Unable to evaluate answer: "
                "previous turn has an empty indicator_id."
            )

        # ------------------------------------------------------
        # Defensive identity check.
        #
        # The EvaluationContext must still describe exactly the
        # same ConversationTurn at the point of evaluation.
        # ------------------------------------------------------

        if evaluation_context.turn_index != previous_turn.index:
            raise RuntimeError(
                "EvaluationContext turn_index does not match "
                "previous_turn.index."
            )

        if evaluation_context.goal_id != str(
            previous_turn.goal_id
        ).strip():
            raise RuntimeError(
                "EvaluationContext goal_id does not match "
                "previous_turn.goal_id."
            )

        if evaluation_context.indicator_id != str(
            previous_turn.indicator_id
        ).strip():
            raise RuntimeError(
                "EvaluationContext indicator_id does not match "
                "previous_turn.indicator_id."
            )

        if evaluation_context.question != str(
            previous_turn.question
        ).strip():
            raise RuntimeError(
                "EvaluationContext question does not match "
                "previous_turn.question."
            )

        # EvaluationService has one canonical public contract:
        # it receives the runtime GoalState plus the identity of the
        # answered indicator. ConversationService owns the session/turn
        # context, so resolve the exact GoalState here and pass only the
        # arguments that EvaluationService accepts.
        goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )

        if goal_state is None:
            raise RuntimeError(
                "Unable to evaluate answer: "
                f"no GoalState found for goal_id '{evaluation_context.goal_id}'."
            )

        try:
            kwargs = dict(
                goal_state=goal_state,
                indicator_id=evaluation_context.indicator_id,
                question=evaluation_context.question,
                answer=evaluation_context.answer,
                turn_index=evaluation_context.turn_index,
            )
            abet_target = ((previous_turn.metadata.get("abet") or {}).get("target"))
            if abet_target:
                kwargs["assessment_target"] = abet_target
            try:
                return evaluate(**kwargs)
            except TypeError as exc:
                # Preserve compatibility with injected legacy evaluation services.
                if "assessment_target" in kwargs and "assessment_target" in str(exc):
                    kwargs.pop("assessment_target", None)
                    return evaluate(**kwargs)
                raise
        except Exception:
            logger.exception(
                (
                    "EvaluationService evaluation failed: "
                    "goal_id=%s indicator_id=%s "
                    "turn_index=%s question=%r"
                ),
                evaluation_context.goal_id,
                evaluation_context.indicator_id,
                evaluation_context.turn_index,
                evaluation_context.question,
            )
            raise

    # ==========================================================
    # Evaluation Snapshot
    # ==========================================================

    def _record_evaluation_snapshot(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
        decision,
    ) -> None:
        """
        Copy values belonging to this answer onto the turn.

        The current IndicatorState may subsequently change when the
        navigator advances, so the turn must contain a historical
        snapshot.
        """

        evidence = self._latest_evidence_for_turn(
            context=context,
            turn=previous_turn,
        )

        if evidence is None:
            raise RuntimeError(
                "No exact evaluation evidence was committed for "
                f"turn {previous_turn.index}."
            )

        assessment: dict[str, Any] = {}

        if evidence is not None:
            for field_name in (
                "achievement_level",
                "confidence",
                "evidence_strength",
                "indicator_demonstrated",
                "feedback",
                "rationale",
                "bloom_level",
                "missing_elements",
            ):
                value = getattr(
                    evidence,
                    field_name,
                    None,
                )

                if value is None:
                    continue

                if (
                    field_name == "bloom_level"
                    and isinstance(value, str)
                    and not value.strip()
                ):
                    continue

                if field_name == "missing_elements":
                    if isinstance(
                        value,
                        (list, tuple),
                    ):
                        value = [
                            str(item)
                            for item in value
                        ]
                    else:
                        value = [
                            str(value)
                        ]

                assessment[field_name] = value

        goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )

        indicator = self._runtime_indicator(
            goal_state,
            previous_turn.indicator_id,
        )

        # ------------------------------------------------------
        # Bloom level fallback
        # ------------------------------------------------------

        if (
            "bloom_level" not in assessment
            and indicator is not None
        ):
            bloom_level = getattr(
                indicator,
                "bloom_level",
                None,
            )

            if bloom_level is not None:
                normalized_bloom_level = str(
                    bloom_level
                ).strip()

                if normalized_bloom_level:
                    assessment["bloom_level"] = (
                        normalized_bloom_level
                    )

        # ------------------------------------------------------
        # Canonical goal-level values come from GoalDecision.
        # ------------------------------------------------------

        for field_name in (
            "coverage",
            "mastery",
            "status",
            "reason",
            "next_indicator",
        ):
            value = getattr(
                decision,
                field_name,
                None,
            )

            if value is not None:
                assessment[field_name] = getattr(
                    value,
                    "value",
                    value,
                )

        assessment["assessment_confidence"] = getattr(
            decision,
            "confidence",
            None,
        )

        assessment["covered"] = bool(
            assessment.get(
                "indicator_demonstrated",
                False,
            )
        )

        # Difficulty values are recorded separately by _adapt_difficulty.
        # Preserve the original question difficulty as well.
        generated_assessment = previous_turn.metadata.get("assessment", {})
        if isinstance(generated_assessment, dict) and generated_assessment.get("difficulty") is not None:
            assessment.setdefault("difficulty", generated_assessment.get("difficulty"))

        if indicator is not None:
            assessment["attempts"] = getattr(
                indicator,
                "attempts",
                None,
            )

            assessment["demonstrated"] = getattr(
                indicator,
                "demonstrated",
                None,
            )

        # ------------------------------------------------------
        # Immutable turn identity.
        # ------------------------------------------------------

        assessment["goal_id"] = previous_turn.goal_id
        assessment["indicator_id"] = previous_turn.indicator_id
        assessment["turn_index"] = previous_turn.index
        assessment["question"] = previous_turn.question

        if previous_turn.metadata is None:
            previous_turn.metadata = {}

        previous_turn.metadata["assessment"] = assessment

    @staticmethod
    def _goal_state_for_turn(
        *,
        context,
        turn: ConversationTurn,
    ):
        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return None

        if not turn.goal_id:
            return None

        get_goal_state = getattr(
            session,
            "get_goal_state",
            None,
        )

        if not callable(get_goal_state):
            return None

        return get_goal_state(turn.goal_id)

    @staticmethod
    def _runtime_indicator(
        goal_state,
        indicator_id: str | None,
    ):
        if (
            goal_state is None
            or not indicator_id
        ):
            return None

        get_indicator = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(get_indicator):
            return get_indicator(
                str(indicator_id)
            )

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if isinstance(indicators, dict):
            return indicators.get(
                str(indicator_id)
            )

        return None

    @classmethod
    def _latest_evidence_for_turn(
        cls,
        *,
        context,
        turn: ConversationTurn,
    ):
        goal_state = cls._goal_state_for_turn(
            context=context,
            turn=turn,
        )

        if (
            goal_state is None
            or not turn.indicator_id
        ):
            return None

        evidence_items = getattr(
            goal_state,
            "evidence",
            None,
        )

        if not evidence_items:
            return None

        target_indicator_id = str(
            turn.indicator_id
        ).strip()

        # ------------------------------------------------------
        # Preferred lookup:
        #
        # exact turn + exact indicator.
        #
        # This prevents Turn N from using evidence belonging to
        # Turn N-1 when the indicator is repeated.
        # ------------------------------------------------------

        for evidence in reversed(evidence_items):
            evidence_turn_index = getattr(
                evidence,
                "turn_index",
                None,
            )

            evidence_indicator_id = str(
                getattr(
                    evidence,
                    "indicator_id",
                    "",
                )
            ).strip()

            if (
                evidence_turn_index == turn.index
                and evidence_indicator_id
                == target_indicator_id
            ):
                return evidence

        # ------------------------------------------------------
        # Legacy compatibility:
        #
        # Evidence from old persisted sessions may not contain
        # turn_index.
        #
        # Only use it when exactly one legacy match exists.
        # ------------------------------------------------------

        legacy_matches = []

        for evidence in evidence_items:
            evidence_turn_index = getattr(
                evidence,
                "turn_index",
                None,
            )

            evidence_indicator_id = str(
                getattr(
                    evidence,
                    "indicator_id",
                    "",
                )
            ).strip()

            if (
                evidence_turn_index is None
                and evidence_indicator_id
                == target_indicator_id
            ):
                legacy_matches.append(evidence)

        if len(legacy_matches) == 1:
            return legacy_matches[0]

        return None

    # ==========================================================
    # Feedback
    # ==========================================================

    def _record_feedback(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> None:
        feedback = self._feedback_for_turn(
            context=context,
            turn=previous_turn,
        )

        if not feedback:
            return

        if previous_turn.metadata is None:
            previous_turn.metadata = {}

        previous_turn.metadata["feedback"] = feedback

    @classmethod
    def _feedback_for_turn(
        cls,
        *,
        context,
        turn: ConversationTurn,
    ) -> str:
        """
        Resolve feedback specifically for the answered turn.

        Priority:
            1. exact evidence for that turn
            2. runtime indicator feedback
            3. decision reason
        """

        evidence = cls._latest_evidence_for_turn(
            context=context,
            turn=turn,
        )

        if evidence is not None:
            feedback = getattr(
                evidence,
                "feedback",
                "",
            )

            if feedback:
                return str(feedback).strip()

        goal_state = cls._goal_state_for_turn(
            context=context,
            turn=turn,
        )

        indicator = cls._runtime_indicator(
            goal_state,
            turn.indicator_id,
        )

        if indicator is not None:
            feedback = getattr(
                indicator,
                "feedback",
                "",
            )

            if feedback:
                return str(feedback).strip()

        decision = getattr(
            turn,
            "decision",
            None,
        )

        reason = getattr(
            decision,
            "reason",
            "",
        )

        return str(reason or "").strip()

    @staticmethod
    def _previous_feedback(context) -> str:
        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return ""

        last_turn = getattr(
            session,
            "last_turn",
            None,
        )

        if last_turn is None:
            turns = getattr(
                session,
                "turns",
                None,
            )

            if turns:
                try:
                    last_turn = turns[-1]
                except (
                    IndexError,
                    TypeError,
                ):
                    last_turn = None

        if last_turn is None:
            return ""

        metadata = getattr(
            last_turn,
            "metadata",
            None,
        )

        if isinstance(metadata, dict):
            feedback = metadata.get(
                "feedback"
            )

            if feedback:
                return str(feedback).strip()

        decision = getattr(
            last_turn,
            "decision",
            None,
        )

        return str(
            getattr(
                decision,
                "reason",
                "",
            )
            or ""
        ).strip()

    # ==========================================================
    # Decision Helpers
    # ==========================================================

    @staticmethod
    def _decision_status(decision) -> str:
        if decision is None:
            return ""

        status = getattr(
            decision,
            "status",
            "",
        )

        if status is None:
            return ""

        return str(
            getattr(
                status,
                "value",
                status,
            )
        ).strip().lower()

    @classmethod
    def _is_terminal_decision(
        cls,
        decision,
    ) -> bool:
        if decision is None:
            return False

        if bool(
            getattr(
                decision,
                "is_complete",
                False,
            )
        ):
            return True

        if bool(
            getattr(
                decision,
                "is_failed",
                False,
            )
        ):
            return True

        status = cls._decision_status(
            decision
        )

        return status in {
            "complete",
            "completed",
            "passed",
            "pass",
            "goal_completed",
            "failed",
            "failure",
            "exhausted",
            "goal_exhausted",
        }

    @classmethod
    def _decision_is_success(
        cls,
        decision,
    ) -> bool:
        if decision is None:
            return False

        if bool(
            getattr(
                decision,
                "is_complete",
                False,
            )
        ):
            return True

        return cls._decision_status(
            decision
        ) in {
            "complete",
            "completed",
            "passed",
            "pass",
            "goal_completed",
        }

    @classmethod
    def _decision_is_failure(
        cls,
        decision,
    ) -> bool:
        if decision is None:
            return False

        if bool(
            getattr(
                decision,
                "is_failed",
                False,
            )
        ):
            return True

        return cls._decision_status(
            decision
        ) in {
            "failed",
            "failure",
            "exhausted",
            "goal_exhausted",
        }

    @staticmethod
    def _preferred_indicator(
        decision,
    ) -> list[str] | None:
        if decision is None:
            return None

        next_indicator = getattr(
            decision,
            "next_indicator",
            None,
        )

        if not next_indicator:
            return None

        if isinstance(
            next_indicator,
            str,
        ):
            return [next_indicator]

        try:
            return [
                str(value)
                for value in next_indicator
            ]
        except TypeError:
            return [str(next_indicator)]

    # ==========================================================
    # Goal State
    # ==========================================================

    def _goal_is_resolved(
        self,
        context,
    ) -> bool:
        goal_state = (
            self.navigator.current_goal_state(
                context
            )
        )

        if goal_state is None:
            return False

        resolved = getattr(
            goal_state,
            "resolved",
            False,
        )

        if callable(resolved):
            resolved = resolved()

        if bool(resolved):
            return True

        is_resolved = getattr(
            goal_state,
            "is_resolved",
            False,
        )

        if callable(is_resolved):
            is_resolved = is_resolved()

        return bool(is_resolved)

    # ==========================================================
    # Indicator Navigation
    # ==========================================================

    def _select_indicator(
        self,
        *,
        context,
        preferred: list[str] | None = None,
    ):
        goal_state = (
            self.navigator.current_goal_state(
                context
            )
        )

        if goal_state is None:
            return None

        if self._goal_is_resolved(context):
            return None

        selected = self.navigator.next_indicator(
            context,
            preferred=preferred,
        )

        if selected is None:
            return None

        indicator_id = self._indicator_id(
            selected
        )

        if indicator_id is None:
            return None

        runtime_indicator = self._get_runtime_indicator(
            goal_state,
            indicator_id,
        )

        if runtime_indicator is None:
            logger.warning(
                (
                    "Navigator selected indicator '%s' "
                    "but it does not exist in GoalState '%s'."
                ),
                indicator_id,
                getattr(
                    goal_state,
                    "goal_id",
                    None,
                ),
            )
            return None

        definition = self._find_indicator_definition(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        if definition is None:
            logger.warning(
                (
                    "Runtime indicator '%s' exists but "
                    "no matching domain definition exists."
                ),
                indicator_id,
            )

        return definition

    def _select_remediation_indicator(
        self,
        *,
        context,
        preferred: list[str] | None = None,
    ):
        """Select an evidence-driven adaptive remediation indicator.

        Historical attempt counts are telemetry only. The interview is
        time-forced, so no per-indicator attempt cap is applied here.
        """
        goal_state = self.navigator.current_goal_state(context)
        if goal_state is None or self._goal_is_resolved(context):
            return None

        planner = getattr(self.navigator, "evidence_planner", None)
        selector = getattr(planner, "select_remediation_indicator", None)
        if not callable(selector):
            return None

        kwargs = {}
        if preferred is not None:
            kwargs["preferred"] = preferred

        selected = selector(goal_state, **kwargs)
        indicator_id = self._indicator_id(selected)
        if indicator_id is None:
            return None
        return self._find_indicator_definition(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

    @staticmethod
    def _indicator_id(selected) -> str | None:
        if selected is None:
            return None

        if isinstance(selected, str):
            value = selected.strip()
            return value or None

        indicator_id = getattr(
            selected,
            "id",
            None,
        )

        if indicator_id is None:
            indicator_id = getattr(
                selected,
                "indicator_id",
                None,
            )

        if indicator_id is None:
            return None

        normalized = str(
            indicator_id
        ).strip()

        return normalized or None

    @staticmethod
    def _get_runtime_indicator(
        goal_state,
        indicator_id: str,
    ):
        getter = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(getter):
            indicator = getter(indicator_id)

            if indicator is not None:
                return indicator

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if isinstance(indicators, dict):
            return indicators.get(indicator_id)

        return None

    @classmethod
    def _find_indicator_definition(
        cls,
        *,
        goal_state,
        indicator_id: str,
    ):
        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        if goal is None:
            return None

        indicators = getattr(
            goal,
            "indicators",
            None,
        )

        if indicators is None:
            return None

        values = getattr(
            indicators,
            "values",
            None,
        )

        if callable(values):
            definitions = values()
        else:
            definitions = indicators

        for definition in definitions:
            definition_id = getattr(
                definition,
                "id",
                None,
            )

            if (
                definition_id is not None
                and str(definition_id).strip()
                == str(indicator_id).strip()
            ):
                return definition

        return None

    # ==========================================================
    # Question Generation
    # ==========================================================

    def _build_question_turn(
        self,
        *,
        context,
        goal,
        indicator,
        index: int,
        excluded_questions: Iterable[str] | None = None,
        selection_source: str = "unknown",
    ) -> ConversationTurn:
        """
        Generate one question and create its ConversationTurn.

        The generated question is validated against the exact
        indicator selected by the navigator before the turn exists.

        This creates the following invariant:

            turn.indicator_id == generated.indicator_id

        and:

            turn.question == generated.question
        """

        goal_id = self._normalize_identity(
            getattr(goal, "id", None),
            "goal.id",
        )

        indicator_id = self._normalize_identity(
            getattr(indicator, "id", None),
            "indicator.id",
        )

        goal_state = self.navigator.current_goal_state(context)

        # QuestionRequest expects the immutable domain GoalIndicator, while
        # several adaptive/minimum-question paths naturally return the
        # mutable runtime IndicatorState.  Normalize at this boundary so the
        # prompt builder never receives runtime state.
        indicator_definition = self._find_indicator_definition(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )
        if indicator_definition is not None:
            indicator = indicator_definition

        target_bloom_level = self._question_bloom_level(
            context=context,
            goal=goal,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        question_strategy = self._question_strategy(
            context=context,
            indicator_id=indicator_id,
            bloom_level=target_bloom_level,
        )
        target_difficulty = self._question_difficulty(
            context=context,
            goal=goal,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        try:
            generated = self._generate_question(
                context=context,
                goal=goal,
                indicator=indicator,
                excluded_questions=excluded_questions,
                expected_difficulty=target_difficulty,
                expected_strategy=question_strategy,
            )
        except QuestionContinuityError:
            # Evidence drift must NOT trigger alternate-indicator navigation.
            # Keep the selected indicator fixed and use the existing deterministic
            # fallback, which is grounded directly in that indicator definition.
            generated = self._fallback_question(
                goal=goal,
                indicator=indicator,
                excluded_questions=self._recent_questions(context.session),
                difficulty=target_difficulty,
                difficulty_reason="continuity_difficulty_lock_fallback",
            )
            logger.warning(
                "Question continuity retries exhausted for indicator=%s; "
                "using an indicator-grounded fallback question.",
                indicator_id,
            )
        except QuestionDifficultyGenerationError:
            # Difficulty violations never change the selected indicator.
            # Fall back on the same indicator with the exact runtime target.
            generated = self._fallback_question(
                goal=goal,
                indicator=indicator,
                excluded_questions=self._recent_questions(context.session),
                difficulty=target_difficulty,
                difficulty_reason="opening_difficulty_lock_fallback",
            )
            logger.warning(
                "Question generation repeatedly violated the fixed difficulty "
                "for indicator=%s; using same-indicator fallback.",
                indicator_id,
            )
        except DuplicateQuestionGenerationError:
            # A generator that repeats itself is a recoverable generation
            # failure, not an interview/lifecycle failure.  In an adaptive
            # interview, first move to another evidence-driven indicator;
            # if none exists, use a deterministic indicator-grounded probe.
            alternate = self._alternate_indicator_for_duplicate(
                context=context,
                current_indicator=indicator,
            )
            if alternate is not None:
                logger.warning(
                    "Duplicate question generation exhausted for indicator=%s; "
                    "switching adaptively to indicator=%s.",
                    indicator_id,
                    getattr(alternate, "id", None),
                )
                return self._build_question_turn(
                    context=context,
                    goal=goal,
                    indicator=alternate,
                    index=index,
                    excluded_questions=excluded_questions,
                    selection_source="duplicate_generation_fallback_alternate",
                )

            generated = self._fallback_question(
                goal=goal,
                indicator=indicator,
                excluded_questions=self._recent_questions(context.session),
                difficulty=target_difficulty,
                difficulty_reason="duplicate_difficulty_lock_fallback",
            )
            logger.warning(
                "Duplicate question generation exhausted for indicator=%s; "
                "using an indicator-grounded fallback question.",
                indicator_id,
            )

        # ------------------------------------------------------
        # Strong generated-question contract.
        # ------------------------------------------------------

        self._validate_generated_question(
            generated,
            expected_indicator_id=indicator_id,
        )

        question = generated.question.strip()
        if self._is_opening_question(context=context, indicator=indicator):
            self._validate_opening_question_structure(
                question,
                bloom_level=target_bloom_level,
                strategy=question_strategy,
            )

        # ------------------------------------------------------
        # Create the turn from the generated object.
        #
        # Never substitute another question source here.
        # ------------------------------------------------------

        turn = self._new_turn(
            index=index,
            question=question,
            goal_id=goal_id,
            indicator_id=indicator_id,
        )

        # Freeze the exact requested difficulty for this question.  The
        # opening-question policy is an invariant, not an LLM suggestion: all
        # student variants in the same published assignment carry the same
        # numeric target, while only the task form varies.
        turn.metadata.setdefault("assessment", {})["difficulty"] = target_difficulty
        turn.metadata["assessment"]["target_difficulty"] = target_difficulty
        turn.metadata["assessment"]["generated_difficulty"] = getattr(
            generated, "difficulty", None
        )
        turn.metadata["assessment"]["difficulty_reason"] = (
            getattr(generated, "difficulty_reason", "")
        )
        turn.metadata["assessment"]["target_bloom_level"] = target_bloom_level
        turn.metadata["assessment"]["question_strategy"] = question_strategy

        if self._is_opening_question(context=context, indicator=indicator):
            turn.metadata["assessment"]["opening_question_contract"] = {
                "version": "12.6.9",
                "variant": f"opening-{str(target_bloom_level).lower()}-"
                f"{self._opening_question_variant_index(context.session) % 3:02d}",
                "goal_id": goal_id,
                "indicator_id": indicator_id,
                "target_bloom": target_bloom_level,
                "target_difficulty": target_difficulty,
                "actual_difficulty": getattr(generated, "difficulty", None),
                "strategy": question_strategy,
                "reasoning_operations": 1,
                "required_subtasks": 2,
                "difficulty_lock": "passed",
            }

        # ------------------------------------------------------
        # v10.7: evidence-continuity audit (safe metadata only).
        # The generation loop has already enforced this contract.
        # ------------------------------------------------------
        try:
            continuity_manager = GoalEvidenceContinuityManager(context.session)
            contract = continuity_manager.focus_contract(
                goal=goal,
                indicator=indicator,
                goal_state=goal_state,
                indicator_id=indicator_id,
            )
            continuity_result = continuity_manager.assess_question(
                question=question,
                indicator=indicator,
                contract=contract,
            )
            turn.metadata["assessment"]["question_continuity"] = {
                "version": continuity_manager.VERSION,
                "accepted": bool(continuity_result.get("accepted")),
                "score": continuity_result.get("score", 0.0),
                "matched_anchor_count": len(continuity_result.get("matched") or []),
                "phrase_match": bool(continuity_result.get("phrase_match")),
                "reason": continuity_result.get("reason", ""),
            }
        except Exception:
            logger.exception(
                "Failed to record question-continuity trace: turn=%s goal_id=%s indicator_id=%s",
                getattr(turn, "index", None),
                goal_id,
                indicator_id,
            )

        # ------------------------------------------------------
        # ABET traceability target (additive)
        # ------------------------------------------------------
        if self.abet_service is not None:
            target = self.abet_service.target_for(
                context.session, goal_id, indicator_id
            )
            if target is not None:
                turn.metadata.setdefault("abet", {})["target"] = target.to_dict()

        # ------------------------------------------------------
        # v9.8: additive adaptive-decision audit trace.
        #
        # This is deliberately metadata-only: it does not participate in
        # navigation, scoring, stopping, or question generation. It stores
        # identifiers and bounded decision factors, never learner answers,
        # prompts, secrets, or raw question text.
        # ------------------------------------------------------
        self._record_adaptive_decision_trace(
            context=context,
            turn=turn,
            goal=goal,
            indicator=indicator,
            goal_state=goal_state,
            target_bloom_level=target_bloom_level,
            question_strategy=question_strategy,
            selection_source=selection_source,
        )

        # ------------------------------------------------------
        # Final identity verification.
        # ------------------------------------------------------

        self._validate_turn_question_identity(
            turn=turn,
            goal_id=goal_id,
            indicator_id=indicator_id,
            question=question,
        )

        logger.info(
            (
                "Generated interview turn: "
                "turn_index=%s goal_id=%s indicator_id=%s "
                "question=%r"
            ),
            turn.index,
            turn.goal_id,
            turn.indicator_id,
            turn.question,
        )

        return turn

    @staticmethod
    def _record_adaptive_decision_trace(
        *,
        context,
        turn: ConversationTurn,
        goal,
        indicator,
        goal_state,
        target_bloom_level: str,
        question_strategy: str,
        selection_source: str,
    ) -> None:
        """Attach a safe, additive explanation of the next-question decision."""
        try:
            runtime_indicator = ConversationService._get_runtime_indicator(
                goal_state, turn.indicator_id
            )
            attempts = getattr(runtime_indicator, "attempts", 0) if runtime_indicator is not None else 0
            confidence = getattr(runtime_indicator, "confidence", 0.0) if runtime_indicator is not None else 0.0
            evidence_strength = getattr(runtime_indicator, "evidence_strength", 0.0) if runtime_indicator is not None else 0.0
            achievement_level = getattr(runtime_indicator, "achievement_level", 0.0) if runtime_indicator is not None else 0.0
            demonstrated = getattr(runtime_indicator, "demonstrated", False) if runtime_indicator is not None else False

            criterion_id = None
            abet = turn.metadata.get("abet", {}) if isinstance(turn.metadata, dict) else {}
            if isinstance(abet, dict):
                target = abet.get("target")
                if isinstance(target, dict):
                    criterion_id = target.get("criterion_id")

            previous_decision = None
            turns = getattr(getattr(context, "session", None), "turns", []) or []
            for candidate in reversed(turns):
                if getattr(candidate, "index", None) >= turn.index:
                    continue
                decision = getattr(candidate, "decision", None)
                if decision is not None:
                    previous_decision = decision
                    break

            decision_status = getattr(previous_decision, "status", None)
            decision_reason = getattr(previous_decision, "reason", None)
            previous_mastery = getattr(previous_decision, "mastery", None)
            previous_confidence = getattr(previous_decision, "confidence", None)
            previous_coverage = getattr(previous_decision, "coverage", None)

            trace = AdaptiveDecisionTrace.build(
                goal_id=turn.goal_id,
                indicator_id=turn.indicator_id,
                selection_source=selection_source,
                target_bloom_level=target_bloom_level,
                question_strategy=question_strategy,
                difficulty=getattr(turn.metadata.get("assessment", {}), "get", lambda *_: None)("difficulty"),
                difficulty_reason=getattr(turn.metadata.get("assessment", {}), "get", lambda *_: "")("difficulty_reason"),
                criterion_id=criterion_id,
                attempts=attempts,
                achievement_level=achievement_level,
                confidence=confidence,
                evidence_strength=evidence_strength,
                demonstrated=demonstrated,
                previous_decision_status=decision_status,
                previous_decision_reason=decision_reason,
                previous_coverage=previous_coverage,
                previous_mastery=previous_mastery,
                previous_confidence=previous_confidence,
            )
            turn.metadata["adaptive_decision_trace"] = trace.to_dict()
        except Exception:
            # Observability must never break a live interview.
            logger.exception(
                "Failed to record adaptive decision trace: turn=%s goal_id=%s indicator_id=%s",
                getattr(turn, "index", None),
                getattr(turn, "goal_id", None),
                getattr(turn, "indicator_id", None),
            )

    @staticmethod
    def _validate_generated_question_difficulty(
        generated: GeneratedQuestion,
        expected_difficulty: float | None,
    ) -> None:
        """Enforce the runtime difficulty target independently of the LLM."""
        if expected_difficulty is None:
            return
        try:
            expected = float(expected_difficulty)
            actual = float(getattr(generated, "difficulty", None))
        except (TypeError, ValueError):
            raise QuestionDifficultyGenerationError(
                "Generated question did not carry a valid runtime difficulty."
            )
        if abs(actual - expected) > 1e-9:
            raise QuestionDifficultyGenerationError(
                f"Generated question difficulty {actual!r} does not match "
                f"runtime target {expected!r}."
            )

    def _generate_question(
        self,
        *,
        context,
        goal,
        indicator,
        excluded_questions: Iterable[str] | None = None,
        expected_difficulty: float | None = None,
        expected_strategy: str | None = None,
    ) -> GeneratedQuestion:
        """
        Ask QuestionGenerator for a question for exactly one goal and
        indicator.

        This method does not modify GoalState, attempts, navigation,
        or evaluation state.
        """

        goal_state = (
            self.navigator.current_goal_state(
                context
            )
        )

        if goal_state is None:
            raise RuntimeError(
                "Unable to generate question: "
                "current GoalState does not exist."
            )

        indicator_id = self._normalize_identity(
            getattr(indicator, "id", None),
            "indicator.id",
        )
        goal_id = self._normalize_identity(
            getattr(goal, "id", None),
            "goal.id",
        )

        # Defensive DTO/domain normalization.  Adaptive runtime paths may
        # pass IndicatorState; the generator/prompt contract requires the
        # immutable GoalIndicator definition (notably its `name`).
        indicator_definition = self._find_indicator_definition(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )
        if indicator_definition is not None:
            indicator = indicator_definition

        target_bloom_level = self._question_bloom_level(
            context=context,
            goal=goal,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        continuity_manager = GoalEvidenceContinuityManager(context.session)
        continuity_contract = continuity_manager.focus_contract(
            goal=goal,
            indicator=indicator,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )
        continuity_guidance = continuity_manager.prompt_guidance(
            continuity_contract
        )

        request = QuestionRequest(
            session=context.session,
            goal=goal,
            indicator=indicator,
            goal_state=goal_state,
            interview_template=(
                self._resolve_interview_template(
                    context
                )
            ),
            previous_feedback=(
                self._previous_feedback(
                    context
                )
            ),
            question_focus=self._append_question_focus(
                self._question_focus(
                    context=context,
                    goal_state=goal_state,
                    indicator_id=indicator_id,
                ),
                continuity_guidance,
            ),
            target_bloom_level=target_bloom_level,
            question_strategy=(
                expected_strategy
                if expected_strategy
                else self._question_strategy(
                    context=context,
                    indicator_id=indicator_id,
                    bloom_level=target_bloom_level,
                )
            ),
            difficulty=(
                expected_difficulty
                if expected_difficulty is not None
                else self._question_difficulty(
                    context=context,
                    goal=goal,
                    goal_state=goal_state,
                    indicator_id=indicator_id,
                )
            ),
            difficulty_reason=self._difficulty_guidance(
                context=context,
                goal_state=goal_state,
                indicator_id=indicator_id,
            ),
            **self._abet_question_target(
                context=context,
                goal_id=goal_id,
                indicator_id=indicator_id,
            ),
        )

        recent_questions = self._recent_questions(
            context.session
        )

        if excluded_questions:
            recent_questions.extend(
                question.strip()
                for question in excluded_questions
                if isinstance(question, str) and question.strip()
            )

        # Preserve order while removing duplicate history entries.
        recent_questions = list(dict.fromkeys(recent_questions))
        last_failure_kind = None

        for attempt in range(
            1,
            self.MAX_DUPLICATE_QUESTION_RETRIES + 1,
        ):
            generated = (
                self.question_generator.generate(
                    request
                )
            )

            # --------------------------------------------------
            # Validate BOTH question and indicator identity.
            # --------------------------------------------------

            self._validate_generated_question(
                generated,
                expected_indicator_id=indicator_id,
            )

            generated.validate_for_indicator(
                indicator_id
            )

            # Difficulty is an assessment contract.  A generator must not
            # silently change the target selected by the runtime, especially
            # for fair opening variants.
            try:
                self._validate_generated_question_difficulty(
                    generated,
                    request.difficulty,
                )
            except QuestionDifficultyGenerationError as exc:
                logger.warning(
                    "QuestionGenerator violated runtime difficulty target; "
                    "retrying attempt %s/%s: %s",
                    attempt,
                    self.MAX_DUPLICATE_QUESTION_RETRIES,
                    exc,
                )
                last_failure_kind = "difficulty"
                request.question_focus = self._append_question_focus(
                    request.question_focus,
                    (
                        f"Keep the exact runtime target difficulty "
                        f"{float(request.difficulty):.4f} and do not increase or "
                        "decrease cognitive or response burden."
                    ),
                )
                continue

            if self._is_opening_question(context=context, indicator=indicator):
                try:
                    self._validate_opening_question_structure(
                        question=generated.question,
                        bloom_level=request.target_bloom_level,
                        strategy=request.question_strategy,
                    )
                except QuestionDifficultyGenerationError as exc:
                    logger.warning(
                        "QuestionGenerator violated opening structural burden; "
                        "retrying attempt %s/%s: %s",
                        attempt,
                        self.MAX_DUPLICATE_QUESTION_RETRIES,
                        exc,
                    )
                    last_failure_kind = "difficulty"
                    request.question_focus = self._append_question_focus(
                        request.question_focus,
                        (
                            "Keep the opening question to one primary reasoning "
                            "operation and no explicit multi-step or advanced edge-case burden."
                        ),
                    )
                    continue

            question = generated.question.strip()

            continuity_result = continuity_manager.validate_question(
                goal=goal,
                indicator=indicator,
                goal_state=goal_state,
                indicator_id=indicator_id,
                question=question,
            )

            if not continuity_result["accepted"]:
                logger.warning(
                    (
                        "QuestionGenerator left the active evidence target; "
                        "retrying attempt %s/%s goal=%s indicator=%s "
                        "reason=%s matched=%s question=%r"
                    ),
                    attempt,
                    self.MAX_DUPLICATE_QUESTION_RETRIES,
                    goal_id,
                    indicator_id,
                    continuity_result.get("reason"),
                    continuity_result.get("matched"),
                    question,
                )
                last_failure_kind = "continuity"
                request.question_focus = self._append_question_focus(
                    request.question_focus,
                    (
                        "The previous generated question was rejected for "
                        "evidence drift. Keep the next question explicitly "
                        "about the selected indicator and elicit evidence for "
                        f"its defining concepts: {', '.join(continuity_contract.get('indicator_terms', [])[:12]) or 'the indicator definition'}. "
                        "Do not switch to an unrelated topic."
                    ),
                )
                continue

            if not self._is_duplicate_question(
                question,
                recent_questions,
            ):
                # --------------------------------------------------
                # Return a normalized GeneratedQuestion.
                #
                # We deliberately retain the generator's indicator
                # identity only after it has passed validation.
                # --------------------------------------------------

                return GeneratedQuestion(
                    question=question,
                    context=generated.context,
                    indicator_id=indicator_id,
                    difficulty=request.difficulty,
                    difficulty_reason=(
                        "opening_difficulty_lock"
                        if not recent_questions and not getattr(context.session, "turns", None)
                        else getattr(generated, "difficulty_reason", request.difficulty_reason)
                    ),
                )

            last_failure_kind = "duplicate"
            logger.warning(
                (
                    "QuestionGenerator returned duplicate "
                    "question attempt %s/%s; "
                    "goal=%s indicator=%s question=%r"
                ),
                attempt,
                self.MAX_DUPLICATE_QUESTION_RETRIES,
                getattr(
                    goal,
                    "id",
                    None,
                ),
                indicator_id,
                question,
            )

            request.question_focus = (
                self._append_question_focus(
                    request.question_focus,
                    (
                        "Generate a materially different "
                        "question. Do not repeat or paraphrase "
                        "a recent question."
                    ),
                )
            )

        if last_failure_kind == "continuity":
            raise QuestionContinuityError(
                "QuestionGenerator repeatedly left the active evidence target "
                f"after {self.MAX_DUPLICATE_QUESTION_RETRIES} attempts."
            )

        if last_failure_kind == "difficulty":
            raise QuestionDifficultyGenerationError(
                "QuestionGenerator repeatedly violated the runtime difficulty target "
                f"after {self.MAX_DUPLICATE_QUESTION_RETRIES} attempts."
            )

        raise DuplicateQuestionGenerationError(
            "QuestionGenerator repeatedly returned a duplicate "
            "question after "
            f"{self.MAX_DUPLICATE_QUESTION_RETRIES} attempts."
        )

    def _alternate_indicator_for_duplicate(
        self,
        *,
        context,
        current_indicator,
    ):
        """Return another evidence-driven indicator, if one is available."""
        goal_state = self.navigator.current_goal_state(context)
        if goal_state is None:
            return None

        current_id = self._indicator_id(current_indicator)
        planner = getattr(self.navigator, "evidence_planner", None)

        candidates = []
        remediation_candidates = getattr(
            planner, "remediation_candidates", None
        )
        if callable(remediation_candidates):
            try:
                candidates.extend(remediation_candidates(goal_state))
            except TypeError:
                candidates.extend(remediation_candidates(goal_state, preferred=None))

        assessable = getattr(planner, "candidates", None)
        if callable(assessable):
            try:
                candidates.extend(assessable(goal_state))
            except TypeError:
                candidates.extend(assessable(goal_state, preferred=None))

        candidates.extend(getattr(goal_state, "indicators", []) or [])

        seen = set()
        for candidate in candidates:
            candidate_id = self._indicator_id(candidate)
            if not candidate_id or candidate_id == current_id or candidate_id in seen:
                continue
            seen.add(candidate_id)
            definition = self._find_indicator_definition(
                goal_state=goal_state,
                indicator_id=candidate_id,
            )
            if definition is not None:
                return definition
        return None

    @staticmethod
    def _fallback_question(
        *,
        goal,
        indicator,
        excluded_questions=None,
        difficulty: float | None = None,
        difficulty_reason: str = "duplicate_generation_fallback",
    ) -> GeneratedQuestion:
        """Create a deterministic, indicator-grounded probe that is not a recent repeat."""
        indicator_id = str(getattr(indicator, "id", "")).strip()
        name = str(getattr(indicator, "name", "")).strip()
        description = str(getattr(indicator, "description", "") or "").strip()
        topic = description or name or indicator_id or str(getattr(goal, "title", "the topic"))
        candidates = [
            (
                f"Explain {topic} in your own words, give a concrete example, "
                "and describe how you would verify that your approach is correct."
            ),
            (
                f"Describe how you would apply {topic} to a practical problem, "
                "show the key steps, and explain how you would check the result."
            ),
            (
                f"Compare two valid ways of demonstrating {topic}, give a concrete "
                "example, and explain what evidence would show that the approach is correct."
            ),
            (
                f"Walk through a new example involving {topic}, identify the critical "
                "reasoning step, and explain how you would verify your answer."
            ),
        ]
        excluded = {
            str(q).strip()
            for q in (excluded_questions or [])
            if isinstance(q, str) and q.strip()
        }
        question = next((candidate for candidate in candidates if candidate not in excluded), candidates[0])
        return GeneratedQuestion(
            question=question,
            context="Deterministic fallback used after repeated duplicate generation.",
            indicator_id=indicator_id,
            difficulty=(
                difficulty
                if difficulty is not None
                else getattr(indicator, "difficulty", None)
            ),
            difficulty_reason=difficulty_reason,
        )

    @staticmethod
    def _validate_generated_question(
        generated,
        *,
        expected_indicator_id: str,
    ) -> None:
        """
        Validate the QuestionGenerator contract.

        A generated question is not accepted merely because it has
        text. It must also identify the indicator for which it was
        generated.
        """

        if generated is None:
            raise RuntimeError(
                "QuestionGenerator returned no question."
            )

        if not isinstance(
            generated,
            GeneratedQuestion,
        ):
            raise TypeError(
                "QuestionGenerator must return a "
                "GeneratedQuestion."
            )

        question = getattr(
            generated,
            "question",
            None,
        )

        if not isinstance(
            question,
            str,
        ) or not question.strip():
            raise RuntimeError(
                "QuestionGenerator returned an invalid question."
            )

        generated_indicator_id = getattr(
            generated,
            "indicator_id",
            None,
        )

        if generated_indicator_id is None:
            raise RuntimeError(
                "QuestionGenerator returned a question "
                "without indicator_id."
            )

        generated_indicator_id = str(
            generated_indicator_id
        ).strip()

        if not generated_indicator_id:
            raise RuntimeError(
                "QuestionGenerator returned an empty indicator_id."
            )

        expected_indicator_id = str(
            expected_indicator_id
        ).strip()

        if not expected_indicator_id:
            raise RuntimeError(
                "ConversationService cannot validate a generated "
                "question against an empty indicator_id."
            )

        if generated_indicator_id != expected_indicator_id:
            raise RuntimeError(
                "QuestionGenerator returned a question for the "
                "wrong indicator: "
                f"generated={generated_indicator_id!r}, "
                f"expected={expected_indicator_id!r}."
            )

    @staticmethod
    def _validate_turn_question_identity(
        *,
        turn: ConversationTurn,
        goal_id: str,
        indicator_id: str,
        question: str,
    ) -> None:
        """
        Verify that the newly created ConversationTurn contains
        exactly the identity that was generated.
        """

        actual_goal_id = str(
            getattr(
                turn,
                "goal_id",
                "",
            )
            or ""
        ).strip()

        actual_indicator_id = str(
            getattr(
                turn,
                "indicator_id",
                "",
            )
            or ""
        ).strip()

        actual_question = str(
            getattr(
                turn,
                "question",
                "",
            )
            or ""
        ).strip()

        if actual_goal_id != goal_id:
            raise RuntimeError(
                "ConversationTurn goal identity mismatch: "
                f"turn={actual_goal_id!r}, "
                f"expected={goal_id!r}."
            )

        if actual_indicator_id != indicator_id:
            raise RuntimeError(
                "ConversationTurn indicator identity mismatch: "
                f"turn={actual_indicator_id!r}, "
                f"expected={indicator_id!r}."
            )

        if actual_question != question:
            raise RuntimeError(
                "ConversationTurn question identity mismatch."
            )

    @staticmethod
    def _normalize_identity(
        value,
        field_name: str,
    ) -> str:
        if value is None:
            raise RuntimeError(
                f"{field_name} is required."
            )

        normalized = str(value).strip()

        if not normalized:
            raise RuntimeError(
                f"{field_name} cannot be empty."
            )

        return normalized

    @classmethod
    def _recent_questions(
        cls,
        session,
    ) -> list[str]:
        turns = getattr(
            session,
            "turns",
            [],
        )

        questions: list[str] = []

        for turn in turns:
            question = getattr(
                turn,
                "question",
                "",
            )

            if not isinstance(
                question,
                str,
            ):
                continue

            normalized = question.strip()

            if not normalized:
                continue

            if (
                cls._normalize_question_text(
                    normalized
                )
                == cls._normalize_question_text(
                    cls.COMPLETION_MESSAGE
                )
            ):
                continue

            questions.append(normalized)

        return questions[
            -cls.QUESTION_HISTORY_LIMIT:
        ]

    @staticmethod
    def _normalize_question_text(
        question: str,
    ) -> str:
        value = str(
            question or ""
        ).strip().lower()

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        value = re.sub(
            r"[^\w\s]",
            "",
            value,
        )

        return value

    @classmethod
    def _is_duplicate_question(
        cls,
        question: str,
        previous_questions: Iterable[str],
    ) -> bool:
        normalized = cls._normalize_question_text(
            question
        )

        if not normalized:
            return True

        return any(
            normalized
            == cls._normalize_question_text(previous)
            for previous in previous_questions
        )

    @staticmethod
    def _latest_evidence_for_indicator(
        context,
        indicator_id: str,
    ):
        """Return the newest evidence snapshot for an indicator, if available."""
        goal_state = None
        navigator = getattr(context, "navigator", None)
        getter = getattr(navigator, "current_goal_state", None)
        if callable(getter):
            try:
                goal_state = getter(context)
            except (TypeError, AttributeError):
                goal_state = None
        if goal_state is None:
            goal_state = getattr(context, "goal_state", None)
        evidence_items = (
            getattr(goal_state, "evidence", None)
            if goal_state is not None
            else None
        )
        if not evidence_items:
            return None
        for evidence in reversed(evidence_items):
            if str(getattr(evidence, "indicator_id", "")).strip() == str(indicator_id).strip():
                return evidence
        return None

    @staticmethod
    def _append_question_focus(
        current: str,
        additional: str,
    ) -> str:
        current = (
            current or ""
        ).strip()

        additional = (
            additional or ""
        ).strip()

        if not current:
            return additional

        if not additional:
            return current

        return f"{current}\n{additional}"

    @classmethod
    def _opening_question_variant_index(cls, session) -> int:
        """Return the stable opening variant assigned to one session.

        Published multi-student assignments store a round-robin variant at
        enrollment time so students in the same assignment do not depend on
        random UUID hash collisions.  Standalone sessions retain the previous
        stable session-id hash behavior.
        """
        metadata = getattr(session, "metadata", {}) or {}
        assigned = metadata.get("opening_question_variant") if isinstance(metadata, dict) else None
        try:
            if assigned is not None:
                value = int(assigned)
                if value >= 0:
                    return value
        except (TypeError, ValueError):
            pass

        session_id = str(getattr(session, "id", "") or "").strip()
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    @classmethod
    def _opening_question_diversity_guidance(cls, session, *, bloom_level: str = "understand") -> str:
        """Return a difficulty-equivalent opening task shape.

        Fairness rule: opening variants never alter the runtime difficulty,
        Bloom target, indicator, ABET target, evidence contract, or response
        burden class.  They only change the surface task form.
        """
        bloom = str(bloom_level or "understand").lower().rsplit(".", 1)[-1]
        strategies = {
            "remember": (
                "recall the key concept and give one minimal example",
                "state the key concept and give one minimal example in a different context",
                "identify the key concept and give one minimal example",
            ),
            "understand": (
                "explain the concept using one concrete example",
                "interpret one concrete example and explain the principle it illustrates",
                "describe the concept in one concrete context and explain the principle it illustrates",
            ),
            "apply": (
                "apply the concept to one short practical scenario and explain the key step",
                "apply the concept to one small example and explain the key step",
                "apply the concept to one new but simple case and explain the key step",
            ),
            "analyze": (
                "analyze one small case, identify one key relationship, and explain it",
                "analyze one small case, identify one key relationship, and explain why it matters",
                "analyze one small case, identify one key relationship, and explain its effect",
            ),
            "evaluate": (
                "judge one proposed approach against the indicator and justify the judgment",
                "judge one proposed approach against the indicator and justify the key reason",
                "judge one proposed approach against the indicator and justify one key criterion",
            ),
            "create": (
                "design one small solution that demonstrates the indicator and justify one key choice",
                "propose one small solution that demonstrates the indicator and justify one key choice",
                "construct one minimal solution that demonstrates the indicator and justify one key choice",
            ),
        }
        variants = strategies.get(bloom, strategies["understand"])
        index = cls._opening_question_variant_index(session) % len(variants)
        key = f"opening-{bloom}-{index:02d}"
        return (
            "Opening-question diversity/fairness contract is mandatory. Use this task shape: "
            f"{variants[index]}. Strategy variant: {key}. "
            "This variant is difficulty-equivalent to the other opening variants: "
            "keep the same selected indicator, Bloom level, target difficulty, ABET criterion, "
            "evidence requirements, and approximately one primary reasoning operation "
            "with one concise justification. Do not add extra sub-tasks, multi-step "
            "implementation, advanced edge cases, or hidden prerequisites. Do not "
            "mention this contract or the variant."
        )

    @staticmethod
    def _is_opening_question(*, context, indicator) -> bool:
        attempts = getattr(indicator, "attempts", 0)
        session = getattr(context, "session", None)
        return attempts == 0 and session is not None and not getattr(session, "turns", None)

    @staticmethod
    def _validate_opening_question_structure(question: str, *, bloom_level: str, strategy: str) -> None:
        """Apply a conservative structural guard to opening-question burden.

        This is intentionally not a semantic difficulty classifier. It only
        rejects obvious multi-task/advanced forms so the runtime numeric
        difficulty lock is not undermined by an over-complex generated form.
        """
        text = str(question or "").strip()
        lowered = text.lower()
        if not text or len(text) > 900:
            raise QuestionDifficultyGenerationError("Opening question exceeds the structural burden limit.")
        if "1." in lowered and "2." in lowered:
            raise QuestionDifficultyGenerationError("Opening question contains an explicit multi-step list.")
        if "step 1" in lowered and "step 2" in lowered:
            raise QuestionDifficultyGenerationError("Opening question contains multiple explicit steps.")
        if text.count("?") > 2:
            raise QuestionDifficultyGenerationError("Opening question contains too many explicit question tasks.")
        if any(token in lowered for token in ("edge case", "corner case", "multiple edge cases")):
            raise QuestionDifficultyGenerationError("Opening question introduces advanced edge-case burden.")

    @classmethod
    def _question_focus(
        cls,
        *,
        context,
        goal_state,
        indicator_id: str,
        bloom_level: str = "understand",
    ) -> str:
        indicator = cls._get_runtime_indicator(
            goal_state,
            indicator_id,
        )

        if indicator is None:
            return ""

        attempts = getattr(
            indicator,
            "attempts",
            0,
        )

        focus_parts: list[str] = []

        # Each independently created student session can otherwise receive
        # the same deterministic opening prompt (same goal/indicator, no
        # question history), which makes the first question identical across
        # published interviews.  Keep the learning target unchanged, but give
        # the opening generation a stable, session-specific task shape.
        session = getattr(context, "session", None)
        if attempts == 0 and session is not None and not getattr(session, "turns", None):
            focus_parts.append(
                cls._opening_question_diversity_guidance(
                    session,
                    bloom_level=bloom_level,
                )
            )

        if attempts > 0:
            focus_parts.append(
                (
                    "This is a follow-up attempt for the same "
                    "indicator. Ask a materially different question."
                )
            )

        feedback = getattr(
            indicator,
            "feedback",
            "",
        )

        if feedback:
            focus_parts.append(
                (
                    "Use previous evaluation feedback to target "
                    "missing or uncertain understanding."
                )
            )

        if cls._recent_questions(context.session):
            focus_parts.append(
                (
                    "Do not repeat recent questions. Change the "
                    "scenario, reasoning angle, example, or task."
                )
            )

        return " ".join(focus_parts)

    @staticmethod
    def _abet_question_target(*, context, goal_id: str, indicator_id: str) -> dict[str, Any]:
        """Resolve the current ABET criterion without changing v7.x navigation."""
        service = getattr(context, "abet_service", None)
        if service is not None:
            target = service.target_for(context.session, goal_id, indicator_id)
            if target is not None:
                return {"criterion_id": target.criterion_id, "criterion_description": target.criterion_description}
        return {"criterion_id": None, "criterion_description": ""}

    # ==========================================================
    # Semantic Question Diversity
    # ==========================================================

    _QUESTION_STRATEGIES = (
        "explain",
        "apply_scenario",
        "implement",
        "diagnose",
        "compare",
        "trace_predict",
        "justify_evaluate",
        "design_create",
        "edge_case",
    )

    _STRATEGY_KEYWORDS = {
        "explain": ("explain", "describe", "what is", "how does", "why does"),
        "apply_scenario": ("scenario", "situation", "how would you", "given", "suppose"),
        "implement": ("write", "implement", "code", "function", "program", "implementing"),
        "diagnose": ("debug", "diagnose", "fix", "bug", "error", "wrong", "fails"),
        "compare": ("compare", "contrast", "difference", "versus", "vs"),
        "trace_predict": ("trace", "predict", "output", "what happens", "result"),
        "justify_evaluate": ("justify", "evaluate", "defend", "critique", "tradeoff", "best"),
        "design_create": ("design", "create", "propose", "architect", "build"),
        "edge_case": ("edge case", "boundary", "invalid", "exception", "failure case"),
    }

    @classmethod
    def _question_strategy(
        cls,
        *,
        context,
        indicator_id: str,
        bloom_level: str,
    ) -> str:
        """Choose a task form that varies from recent questions for this indicator.

        This is a generation-shaping signal only. It never changes the selected
        indicator, ABET target, Bloom compliance floor, difficulty, navigation,
        attempts, or time-forced lifecycle.
        """
        recent = []
        for turn in getattr(getattr(context, "session", None), "turns", []) or []:
            if str(getattr(turn, "indicator_id", "")).strip() != str(indicator_id).strip():
                continue
            question = getattr(turn, "question", "")
            if isinstance(question, str) and question.strip():
                recent.append(question.strip().lower())

        used = {cls._infer_question_strategy(q) for q in recent[-6:]}
        used.discard("")

        # Bloom-aware ordering keeps the task form compatible with the requested
        # cognitive demand while still rotating the actual task structure.
        order = {
            "remember": ("explain", "compare", "trace_predict", "apply_scenario"),
            "understand": ("explain", "compare", "apply_scenario", "trace_predict"),
            "apply": ("apply_scenario", "implement", "diagnose", "edge_case", "trace_predict"),
            "analyze": ("diagnose", "compare", "trace_predict", "apply_scenario", "edge_case"),
            "evaluate": ("justify_evaluate", "compare", "diagnose", "edge_case", "apply_scenario"),
            "create": ("design_create", "justify_evaluate", "apply_scenario", "edge_case", "diagnose"),
        }.get(str(bloom_level).lower(), cls._QUESTION_STRATEGIES)

        # Stronger opening strategy for published multi-student sessions:
        # the assignment enrollment assigns a stable round-robin variant to
        # each student.  This means the first three students in the same
        # assignment receive three different Bloom-compatible task forms,
        # instead of relying only on an LLM to honor free-form diversity text.
        session = getattr(context, "session", None)
        if not recent and session is not None and not getattr(session, "turns", None):
            # The opening strategy is selected from the Bloom-compatible
            # calibrated set.  It is a task-form rotation only; the runtime
            # difficulty is locked separately in _generate_question().
            opening_order = {
                "remember": ("explain", "trace_predict", "compare"),
                "understand": ("explain", "trace_predict", "compare"),
                "apply": ("apply_scenario", "trace_predict", "implement"),
                "analyze": ("diagnose", "trace_predict", "compare"),
                "evaluate": ("justify_evaluate", "compare", "diagnose"),
                "create": ("design_create", "apply_scenario", "justify_evaluate"),
            }.get(str(bloom_level).lower(), ("explain", "trace_predict", "compare"))
            variant = cls._opening_question_variant_index(session)
            return opening_order[variant % len(opening_order)]

        for strategy in order:
            if strategy not in used:
                return strategy
        return order[0] if order else "apply_scenario"

    @classmethod
    def _infer_question_strategy(cls, question: str) -> str:
        normalized = cls._normalize_question_text(question)
        if not normalized:
            return ""
        for strategy, keywords in cls._STRATEGY_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return strategy
        return ""

    # ==========================================================
    # Adaptive Bloom / Cognitive Demand
    # ==========================================================

    _BLOOM_ORDER = (
        "remember",
        "understand",
        "apply",
        "analyze",
        "evaluate",
        "create",
    )

    def _question_bloom_level(
        self,
        *,
        context,
        goal,
        goal_state,
        indicator_id: str,
    ) -> str:
        """Choose cognitive demand without changing the goal's required Bloom level.

        The goal Bloom level is the compliance floor. When the latest evidence for
        this indicator is strong and sufficiently reliable, the next question may
        move one level higher to increase cognitive demand. Weak/uncertain evidence
        holds at the goal level rather than dropping below the learning outcome.
        """
        base = str(getattr(goal, "bloom_level", "understand") or "understand").lower()
        if "." in base:
            base = base.rsplit(".", 1)[-1]
        if base not in self._BLOOM_ORDER:
            base = "understand"

        evidence = self._latest_evidence_for_indicator(context, indicator_id)
        if evidence is None:
            return base

        try:
            achievement = int(getattr(evidence, "achievement_level", 0) or 0)
        except (TypeError, ValueError):
            achievement = 0
        try:
            confidence = float(getattr(evidence, "confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            strength = float(getattr(evidence, "evidence_strength", 0.0) or 0.0)
        except (TypeError, ValueError):
            strength = 0.0

        # Promotion requires strong demonstrated performance and evidence quality.
        # This prevents Bloom escalation from a single weak or uncertain answer.
        strong = (
            achievement >= 5
            and confidence >= 0.70
            and strength >= 0.70
            and bool(getattr(evidence, "indicator_demonstrated", False))
        )
        if not strong:
            return base

        index = self._BLOOM_ORDER.index(base)
        return self._BLOOM_ORDER[min(index + 1, len(self._BLOOM_ORDER) - 1)]

    # ==========================================================
    # Adaptive Difficulty
    # ==========================================================

    def _question_difficulty(
        self,
        *,
        context,
        goal,
        goal_state,
        indicator_id: str,
    ) -> float | None:
        configuration = getattr(context, "configuration", None)
        policy = getattr(configuration, "difficulty_policy", None)
        if str(getattr(policy, "value", policy or "adaptive")).lower() == "fixed":
            return self.difficulty_controller.initial_difficulty(
                goal=goal,
                indicator=self._get_runtime_indicator(goal_state, indicator_id),
            )

        indicator_state = self._get_runtime_indicator(goal_state, indicator_id)
        if indicator_state is None:
            return None

        # GoalManager is the authoritative goal-level challenge target.
        # Indicator-level difficulty remains available for history and
        # diagnostics, but the next question must follow the goal's latest
        # strong/medium/weak direction.
        return GoalManager(context.session).target_difficulty(goal_state)

    def _difficulty_guidance(
        self,
        *,
        context,
        goal_state,
        indicator_id: str,
    ) -> str:
        indicator = self._get_runtime_indicator(goal_state, indicator_id)
        if indicator is None:
            return "Use an appropriate challenge level for the learner."

        reason = getattr(indicator, "last_difficulty_reason", "")
        if reason:
            return (
                "This difficulty was selected from the learner's previous "
                "performance. Follow the target challenge without mentioning "
                "the internal score or difficulty number. " + str(reason)
            )
        return "Use the target difficulty while preserving the indicator and Bloom level."

    def _adapt_difficulty(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> None:
        configuration = getattr(context, "configuration", None)
        policy = getattr(configuration, "difficulty_policy", None)
        policy_value = str(getattr(policy, "value", policy or "adaptive")).lower()
        if policy_value != "adaptive":
            return

        goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )
        if goal_state is None:
            return

        indicator = self._get_runtime_indicator(
            goal_state,
            previous_turn.indicator_id,
        )
        if indicator is None:
            return

        evidence = self._latest_evidence_for_turn(
            context=context,
            turn=previous_turn,
        )
        if evidence is None:
            logger.warning(
                "Skipping adaptive difficulty: no exact evidence for turn %s.",
                previous_turn.index,
            )
            return

        controller = self.difficulty_controller
        configuration = getattr(context, "configuration", None)
        if configuration is not None:
            # Session configuration wins over controller defaults.
            controller = AdaptiveDifficultyController(
                minimum=getattr(configuration, "difficulty_min", controller.minimum),
                maximum=getattr(configuration, "difficulty_max", controller.maximum),
                step=getattr(configuration, "difficulty_step", controller.step),
                high_threshold=getattr(configuration, "difficulty_high_threshold", controller.high_threshold),
                low_threshold=getattr(configuration, "difficulty_low_threshold", controller.low_threshold),
                smoothing=getattr(configuration, "difficulty_smoothing", controller.smoothing),
                strong_streak=getattr(configuration, "difficulty_require_consecutive_strong", controller.strong_streak),
                weak_streak=getattr(configuration, "difficulty_require_consecutive_weak", controller.weak_streak),
            )
            self.difficulty_controller = controller

        decision = controller.update(
            indicator=indicator,
            evidence=evidence,
        )

        # Goal-level adaptation is authoritative for the next question.
        # Observation already happened once in next_turn before this method.
        goal_manager = GoalManager(context.session)
        goal_target = goal_manager.target_difficulty(goal_state)
        indicator.difficulty = goal_target
        if hasattr(indicator, "last_difficulty_reason"):
            goal_snapshot = goal_manager.snapshot(goal_state)
            indicator.last_difficulty_reason = str(
                goal_snapshot.get("goals", {})
                .get(goal_manager._goal_id(goal_state), {})
                .get("reason", decision.reason)
            )

        assessment = previous_turn.metadata.setdefault("assessment", {})
        assessment["difficulty_before"] = decision.previous_difficulty
        assessment["difficulty_after"] = decision.new_difficulty
        assessment["difficulty_performance"] = decision.performance
        assessment["difficulty_direction"] = decision.direction
        assessment["difficulty_reason"] = decision.reason

        logger.info(
            "Adaptive difficulty: turn=%s indicator=%s %.2f -> %.2f (%s)",
            previous_turn.index,
            previous_turn.indicator_id,
            decision.previous_difficulty,
            decision.new_difficulty,
            decision.direction,
        )

    # ==========================================================
    # Template
    # ==========================================================

    @classmethod
    def _resolve_interview_template(
        cls,
        context,
    ) -> InterviewTemplate:
        configuration = getattr(
            context,
            "configuration",
            None,
        )

        template = getattr(
            configuration,
            "interview_template",
            None,
        )

        if template is not None:
            return template

        return InterviewTemplate(
            id=cls.DEFAULT_TEMPLATE_ID,
            name=cls.DEFAULT_TEMPLATE_NAME,
            goal_model_id=getattr(
                context.goal_model,
                "id",
                "",
            ),
        )

    # ==========================================================
    # Goal Advancement
    # ==========================================================

    def _advance_after_goal(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> ConversationTurn:
        goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )
        if goal_state is not None:
            outcome = "completed" if getattr(goal_state, "completed", False) else "failed"
            GoalTimeManager(context.session).finish_goal(
                previous_turn.goal_id,
                outcome=outcome,
            )
        self._resolve_current_goal(
            context=context,
            previous_turn=previous_turn,
        )

        next_goal = self.navigator.advance_goal(
            context
        )

        if next_goal is None:
            if self.navigator.finished(context):
                return self._finish_previous_turn(
                    context=context,
                    previous_turn=previous_turn,
                )

            return self._advance_until_question(
                context=context,
                start_index=previous_turn.index,
                excluded_questions=[previous_turn.question],
            )

        indicator = self._select_indicator(
            context=context
        )

        if indicator is None:
            return self._advance_until_question(
                context=context,
                start_index=previous_turn.index,
                excluded_questions=[previous_turn.question],
            )

        return self._build_question_turn(
            context=context,
            goal=next_goal,
            indicator=indicator,
            index=previous_turn.index + 1,
            excluded_questions=[previous_turn.question],
            selection_source="new_goal_selection",
        )

    def _resolve_current_goal(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> None:
        decision = getattr(
            previous_turn,
            "decision",
            None,
        )

        if decision is None:
            return

        goal_state = self._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        )

        if goal_state is None:
            goal_state = (
                self.navigator.current_goal_state(
                    context
                )
            )

        if goal_state is None:
            raise RuntimeError(
                "Terminal decision exists but the corresponding "
                "GoalState cannot be resolved."
            )

        if self._decision_is_success(decision):
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

            logger.info(
                "Goal '%s' marked PASSED.",
                self._goal_state_id(goal_state),
            )

            return

        if self._decision_is_failure(decision):
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

            logger.info(
                "Goal '%s' marked FAILED/EXHAUSTED.",
                self._goal_state_id(goal_state),
            )

    @staticmethod
    def _goal_state_id(goal_state):
        goal_id = getattr(
            goal_state,
            "goal_id",
            None,
        )

        if goal_id is not None:
            return goal_id

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        return getattr(
            goal,
            "id",
            None,
        )

    def _advance_until_question(
        self,
        *,
        context,
        start_index: int,
        excluded_questions: Iterable[str] | None = None,
    ) -> ConversationTurn:
        max_iterations = self._max_goal_iterations(
            context
        )

        for _ in range(max_iterations):
            goal = self.navigator.current_goal(
                context
            )

            if goal is None:
                if self.navigator.finished(context):
                    return self._complete_turn(
                        session=context.session,
                        index=start_index + 1,
                    )

                break

            if self._goal_is_resolved(context):
                next_goal = (
                    self.navigator.advance_goal(
                        context
                    )
                )

                if next_goal is not None:
                    continue

                if self.navigator.finished(context):
                    return self._complete_turn(
                        session=context.session,
                        index=start_index + 1,
                    )

                continue

            indicator = self._select_indicator(
                context=context
            )

            if indicator is not None:
                return self._build_question_turn(
                    context=context,
                    goal=goal,
                    indicator=indicator,
                    index=start_index + 1,
                    excluded_questions=excluded_questions,
                )

            next_goal = self.navigator.advance_goal(
                context
            )

            if next_goal is not None:
                continue

            if self.navigator.finished(context):
                return self._complete_turn(
                    session=context.session,
                    index=start_index + 1,
                )

            break

        if self.navigator.finished(context):
            return self._complete_turn(
                session=context.session,
                index=start_index + 1,
            )

        raise RuntimeError(
            "Unable to navigate to the next interview question: "
            "navigator could not resolve the current goal."
        )

    @staticmethod
    def _max_goal_iterations(context) -> int:
        goal_model = getattr(
            context,
            "goal_model",
            None,
        )

        goal_count = getattr(
            goal_model,
            "goal_count",
            None,
        )

        if (
            isinstance(goal_count, int)
            and goal_count >= 0
        ):
            return max(
                1,
                goal_count + 1,
            )

        goals = getattr(
            goal_model,
            "goals",
            None,
        )

        if goals is not None:
            try:
                return max(
                    1,
                    len(goals) + 1,
                )
            except TypeError:
                pass

        return 100

    # ==========================================================
    # Time-forced continuation
    # ==========================================================

    @staticmethod
    def _time_forced_enabled(context) -> bool:
        session = getattr(context, "session", None)
        configuration = getattr(session, "configuration", None)
        if configuration is None:
            return False
        enabled = getattr(configuration, "enable_time_management", True)
        return bool(enabled and getattr(configuration, "duration_seconds", None) is not None)

    def _is_last_goal(self, context) -> bool:
        manager = getattr(self.navigator, "goal_manager", None)
        if manager is None:
            return False
        index = getattr(manager, "_current_index", None)
        states = getattr(manager, "_goal_states", None)
        if isinstance(index, int) and states is not None:
            try:
                return bool(states) and index == len(states) - 1
            except TypeError:
                return False
        return False

    def _time_forced_continuation_indicator(
        self,
        *,
        context,
        goal_state,
        preferred: list[str] | None = None,
        current_indicator_id: str | None = None,
    ):
        """Choose a valid indicator for continued final-goal assessment.

        This is deliberately separate from remediation eligibility. A final
        goal may be academically resolved while the time-forced interview is
        still running; in that state every valid indicator remains a legal
        question target. Preferred indicators are honored first, then the
        previous indicator is reused when it is the only available target,
        otherwise the first valid goal indicator is selected.
        """
        preferred_ids = [
            str(value).strip()
            for value in (preferred or [])
            if str(value).strip()
        ]

        indicators = list(getattr(goal_state, "indicators", []) or [])
        if not indicators:
            return None

        ordered = []
        if preferred_ids:
            ordered.extend(
                indicator
                for indicator in indicators
                if self._indicator_id(indicator) in preferred_ids
            )

        if current_indicator_id:
            ordered.extend(
                indicator
                for indicator in indicators
                if self._indicator_id(indicator) == current_indicator_id
            )

        ordered.extend(indicators)

        seen: set[str] = set()
        for candidate in ordered:
            candidate_id = self._indicator_id(candidate)
            if not candidate_id or candidate_id in seen:
                continue
            seen.add(candidate_id)
            definition = self._find_indicator_definition(
                goal_state=goal_state,
                indicator_id=candidate_id,
            )
            if definition is not None:
                return definition

        return None

    def _continue_time_forced_goal(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
        decision=None,
    ) -> ConversationTurn:
        """Continue assessing the final goal until the time budget expires.

        Academic success/failure remains recorded in GoalState, but it is not
        allowed to terminate a time-forced interview.  The remediation
        selector is intentionally evidence-driven and has no attempt cap.
        """
        goal = self.navigator.current_goal(context)
        goal_state = self.navigator.current_goal_state(context)
        if goal is None or goal_state is None:
            raise RuntimeError(
                "Time-forced continuation requires an active final goal."
            )

        preferred = self._preferred_indicator(decision)
        indicator = self._select_remediation_indicator(
            context=context,
            preferred=preferred,
        )

        # A resolved final goal is an intentional continuation state in a
        # time-forced interview. EvidencePlanner may correctly return no
        # remediation candidates because the indicator is already
        # evidence-sufficient. That must not be interpreted as "no question
        # can be asked": the deadline, not academic resolution, is the hard
        # stop. Fall back to the goal's own indicator definitions so a final
        # goal with one already-mastered indicator can still be probed until
        # time expires. This does not introduce an attempt limit or mutate
        # assessment state.
        if indicator is None:
            indicator = self._time_forced_continuation_indicator(
                context=context,
                goal_state=goal_state,
                preferred=preferred,
                current_indicator_id=previous_turn.indicator_id,
            )

        if indicator is None:
            raise RuntimeError(
                "Time-forced interview cannot select another adaptive question "
                "from the final goal."
            )

        return self._build_question_turn(
            context=context,
            goal=goal,
            indicator=indicator,
            index=previous_turn.index + 1,
            excluded_questions=[previous_turn.question],
            selection_source="time_forced_continuation",
        )

    # ==========================================================
    # Completion
    # ==========================================================

    @staticmethod
    def _time_expired(context) -> bool:
        session = getattr(context, "session", None)
        if session is None:
            return False
        configuration = getattr(session, "configuration", None)
        enabled = getattr(configuration, "enable_time_management", True)
        if not enabled:
            return False
        started_at = getattr(session, "started_at", None)
        if started_at is None:
            return False
        from datetime import datetime, timezone
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        duration = getattr(configuration, "duration_seconds", None)
        if duration is None:
            duration = float(getattr(configuration, "max_minutes", 30) or 30) * 60.0
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = 1800.0
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        return elapsed >= max(30.0, duration)

    @staticmethod
    def _finish_due_to_time(
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> ConversationTurn:
        previous_turn.completed = True
        completion = previous_turn.metadata.setdefault("completion", {})
        completion["reason"] = "time_expired"
        session = context.session
        goal_id = getattr(previous_turn, "goal_id", None)
        goal_state = ConversationService._goal_state_for_turn(
            context=context,
            turn=previous_turn,
        ) if goal_id else None
        if goal_state is not None:
            mark_failed = getattr(goal_state, "mark_failed", None)
            if callable(mark_failed) and not getattr(goal_state, "resolved", False):
                mark_failed()
            GoalTimeManager(session).finish_goal(
                goal_id,
                outcome="failed_global_time",
            )
        mark_completed = getattr(session, "mark_completed", None)
        if not callable(mark_completed):
            raise RuntimeError("Session must provide mark_completed().")
        mark_completed()
        return previous_turn

    @classmethod
    def _complete_turn(
        cls,
        *,
        session,
        index: int,
    ) -> ConversationTurn:
        mark_completed = getattr(
            session,
            "mark_completed",
            None,
        )

        if not callable(mark_completed):
            raise RuntimeError(
                "Session must provide mark_completed()."
            )

        mark_completed()

        return ConversationTurn(
            index=index,
            question=cls.COMPLETION_MESSAGE,
            completed=True,
        )

    def _finish_previous_turn(
        self,
        *,
        context,
        previous_turn: ConversationTurn,
    ) -> ConversationTurn:
        if not self.navigator.finished(context):
            raise RuntimeError(
                "Attempted to complete interview while "
                "an assessable goal still exists."
            )

        previous_turn.completed = True

        mark_completed = getattr(
            context.session,
            "mark_completed",
            None,
        )

        if not callable(mark_completed):
            raise RuntimeError(
                "Session must provide mark_completed()."
            )

        mark_completed()

        return previous_turn

    # ==========================================================
    # Turn Construction
    # ==========================================================

    @staticmethod
    def _new_turn(
        *,
        index: int,
        question: str,
        goal_id: str | None,
        indicator_id: str | None,
    ) -> ConversationTurn:
        return ConversationTurn(
            index=index,
            question=question,
            goal_id=goal_id,
            indicator_id=indicator_id,
        )