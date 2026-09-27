"""
app/assessment/runtime.py

Interview runtime.

AssessmentRuntime is a lightweight execution object that
coordinates an InterviewSession with ConversationService.

Persistent interview state lives in InterviewSession.

Runtime collaborators live in AssessmentContext and the injected
services.

Responsibilities
----------------
- Coordinate ConversationService execution.
- Persist newly-created conversation turns into InterviewSession.
- Synchronize persisted navigation context.
- Synchronize lightweight runtime bookkeeping.
- Synchronize interview completion state.
- Expose interview progress.
- Build the final AssessmentResult.
- Reset the interview runtime.

Non-responsibilities
-------------------
- Answer evaluation.
- Question generation.
- Goal navigation algorithms.
- Assessment reasoning.
- Mastery calculation.
- Confidence calculation.
- Evidence evaluation.
- Persistence transactions.
- Repository access.

Ownership
---------
InterviewSession owns:

- conversation turns;
- GoalState objects;
- current goal identity;
- current indicator identity;
- interview lifecycle;
- session metadata.

ConversationService owns:

- answer processing;
- assessment pipeline invocation;
- assessment decision application;
- next-question selection.

GoalManager / assessment layer owns:

- goal navigation;
- indicator navigation;
- assessment reasoning;
- coverage;
- mastery;
- confidence.

AssessmentRuntime only coordinates those components.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..conversation.service import ConversationService
from ..interview.conversation_turn import ConversationTurn
from ..interview.lifecycle import InterviewLifecycle
from .result_builder import AssessmentResultBuilder
from .goal_time_manager import GoalTimeManager


class AssessmentRuntime:
    """
    Coordinate execution of one InterviewSession.

    AssessmentRuntime is intentionally thin.

    It does not implement assessment algorithms. It delegates
    assessment and conversation decisions to ConversationService
    and persists the resulting runtime state through InterviewSession.
    """

    def __init__(
        self,
        *,
        session,
        context,
        conversation_service: ConversationService,
        result_builder: AssessmentResultBuilder,
    ) -> None:
        if session is None:
            raise ValueError(
                "AssessmentRuntime requires a session."
            )

        if context is None:
            raise ValueError(
                "AssessmentRuntime requires a context."
            )

        if conversation_service is None:
            raise ValueError(
                "AssessmentRuntime requires a "
                "conversation_service."
            )

        if result_builder is None:
            raise ValueError(
                "AssessmentRuntime requires a "
                "result_builder."
            )

        self.session = session
        self.context = context
        self.conversation_service = conversation_service
        self.result_builder = result_builder
        self.goal_time_manager = GoalTimeManager(session)

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def completed(self) -> bool:
        """
        Return whether the interview has completed.

        InterviewSession is authoritative.
        """

        return bool(self.session.completed)

    @property
    def history(self):
        """
        Return the session conversation history.

        InterviewSession owns persistent conversation state.
        """

        return self.session.history

    @property
    def current_turn(self) -> ConversationTurn | None:
        """
        Return the latest persisted conversation turn.
        """

        return self.session.last_turn

    @property
    def turn_count(self) -> int:
        """
        Return the number of persisted conversation turns.
        """

        return self.session.turn_count

    # ==========================================================
    # Conversation
    # ==========================================================

    def next_turn(
        self,
        answer: str | None = None,
    ) -> ConversationTurn:
        """
        Execute the next interview step.

        First invocation
        ----------------
        Creates and persists the first interviewer turn.

        Subsequent invocation
        ---------------------
        Requires a non-empty learner answer.

        ConversationService processes the answer and either:

        1. returns a newly-created next interviewer turn; or
        2. returns the previous turn as the terminal turn.

        AssessmentRuntime does not evaluate the answer itself.

        It only coordinates:

            ConversationService
                    ↓
            InterviewSession
                    ↓
            AssessmentResult
        """

        previous_turn = self.session.last_turn

        # Lifecycle is derived from the persisted conversation state.
        # A stale `session.completed=True` flag must not block a real
        # non-terminal current question. This can happen after a previous
        # request committed navigation but the lifecycle flag was persisted
        # by an older runtime version. Repair it before enforcing the
        # completed-session guard.
        if self.session.completed:
            if previous_turn is not None and not previous_turn.completed and previous_turn.has_question:
                mark_active = getattr(self.session, "mark_active", None)
                if callable(mark_active):
                    mark_active()
                else:
                    self.session.completed = False
                    if hasattr(self.session, "finished_at"):
                        self.session.finished_at = None
            else:
                raise RuntimeError(
                    "Interview already completed."
                )

        # ======================================================
        # First turn
        # ======================================================

        if previous_turn is None:
            return self._start_interview()

        # ======================================================
        # Existing turn
        # ======================================================

        normalized_answer = self._normalize_answer(
            answer
        )

        turn = self.conversation_service.next_turn(
            context=self.context,
            answer=normalized_answer,
            previous_turn=previous_turn,
        )

        # ConversationService enforces the time boundary after evaluation
        # and before generating another question. Keep a defensive check in
        # case a custom ConversationService returns a fresh turn after its
        # own policy hook.
        if turn is not previous_turn and self._time_expired():
            previous_turn.completed = True
            previous_turn.metadata.setdefault("completion", {})["reason"] = "time_expired"
            turn = previous_turn

        if turn is None:
            raise RuntimeError(
                "ConversationService returned no "
                "next interview turn."
            )

        is_new_turn = (
            turn is not previous_turn
        )

        # ------------------------------------------------------
        # The answer belongs to the previous turn.
        #
        # ConversationService normally records it while processing
        # the answer. Runtime only maintains lightweight context
        # bookkeeping here.
        # ------------------------------------------------------


        # ------------------------------------------------------
        # Persist only a genuinely new turn.
        #
        # If ConversationService returns the previous turn as the
        # terminal result, it is already present in the session.
        # ------------------------------------------------------

        if is_new_turn:
            self._persist_new_turn(
                turn
            )

        # ------------------------------------------------------
        # Hard lifecycle invariant.
        #
        # A generated non-terminal question is authoritative evidence
        # that the interview is still active.  Some legacy navigation
        # paths can transiently leave the session.completed flag stale
        # after goal advancement.  Repair that state BEFORE persistence
        # so the next request cannot be rejected as "already completed".
        #
        # Conversely, only an explicitly terminal ConversationTurn may
        # leave the session completed.
        # ------------------------------------------------------
        InterviewLifecycle.synchronize_session(self.session, turn)

        # ------------------------------------------------------
        # Synchronize persisted navigation context.
        # ------------------------------------------------------

        self._synchronize_session_navigation(
            turn
        )
        self._get_goal_time_manager().ensure_goal_started(getattr(turn, "goal_id", None))
        self._sync_goal_time_state(getattr(turn, "goal_id", None))

        # ------------------------------------------------------
        # Synchronize lightweight runtime context.
        # ------------------------------------------------------

        self._synchronize_context_after_turn(
            turn=turn,
            is_new_turn=is_new_turn,
        )

        # ------------------------------------------------------
        # Synchronize lifecycle state.
        #
        # ConversationTurn.completed is the signal that this
        # conversation step terminates the interview.
        #
        # InterviewSession remains the persistent authority.
        # ------------------------------------------------------

        self._synchronize_completion(
            turn
        )

        InterviewLifecycle.assert_session_turn_consistency(
            session=self.session,
            turn=turn,
        )

        return turn

    def _start_interview(self) -> ConversationTurn:
        """
        Create and persist the first interviewer turn and start the
        authoritative wall-clock interview budget.
        """

        self.session.started_at = datetime.now(timezone.utc)
        self.session.finished_at = None
        self.session.completed = False

        turn = self.conversation_service.first_turn(
            self.context
        )

        if turn is None:
            raise RuntimeError(
                "ConversationService returned no "
                "first interview turn."
            )

        self._persist_new_turn(
            turn
        )

        self._synchronize_session_navigation(
            turn
        )
        self._get_goal_time_manager().ensure_goal_started(getattr(turn, "goal_id", None))
        self._sync_goal_time_state(getattr(turn, "goal_id", None))

        self._synchronize_context_after_turn(
            turn=turn,
            is_new_turn=True,
        )

        self._synchronize_completion(
            turn
        )

        return turn

    def _get_goal_time_manager(self) -> GoalTimeManager:
        manager = getattr(self, "goal_time_manager", None)
        if manager is None:
            manager = GoalTimeManager(self.session)
            self.goal_time_manager = manager
        return manager

    def _sync_goal_time_state(self, goal_id: str | None) -> None:
        snapshot = self._get_goal_time_manager().snapshot(goal_id)
        for gid, data in snapshot.get("goals", {}).items():
            state = self.session.get_goal_state(gid)
            if state is None:
                continue
            state.time_budget_seconds = float(data.get("budget_seconds", 0.0))
            state.time_elapsed_seconds = float(data.get("elapsed_seconds", 0.0))
            state.time_remaining_seconds = float(data.get("remaining_seconds", 0.0))
            finished = self._get_goal_time_manager().state.get("finished_goals", {}).get(gid)
            if finished:
                state.time_finished_at = finished.get("finished_at")
                state.time_outcome = finished.get("outcome")
        self.session.metadata["goal_time_snapshot"] = snapshot

    def _goal_time_snapshot(self) -> dict[str, Any]:
        current = getattr(self.session, "current_goal_id", None)
        self._sync_goal_time_state(current)
        return self.session.metadata.get("goal_time_snapshot", {})

    # ==========================================================
    # Time-forced interview policy
    # ==========================================================

    def _duration_seconds(self) -> float:
        configuration = getattr(self.session, "configuration", None)
        value = None
        if isinstance(configuration, dict):
            value = configuration.get("duration_seconds")
            if value is None and configuration.get("max_minutes") is not None:
                value = float(configuration.get("max_minutes")) * 60.0
        elif configuration is not None:
            value = getattr(configuration, "duration_seconds", None)
            if value is None and hasattr(configuration, "max_minutes"):
                minutes = getattr(configuration, "max_minutes", None)
                if minutes is not None:
                    value = float(minutes) * 60.0
        if value is None:
            meta = getattr(self.session, "metadata", {}) or {}
            value = meta.get("duration_seconds")
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 600.0
        return max(30.0, value)

    def _elapsed_seconds(self) -> float:
        started_at = getattr(self.session, "started_at", None)
        if started_at is None:
            return 0.0
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())

    def _time_expired(self) -> bool:
        configuration = getattr(self.session, "configuration", None)
        # Explicit opt-out remains supported for compatibility with older
        # internal callers; the API's time-forced interviewer uses the
        # default enabled behaviour.
        enabled = getattr(configuration, "enable_time_management", True)
        return bool(enabled) and self._elapsed_seconds() >= self._duration_seconds()

    # ==========================================================
    # Input
    # ==========================================================

    @staticmethod
    def _normalize_answer(
        answer: str | None,
    ) -> str:
        """
        Validate and normalize a learner answer.

        Input validation belongs at the runtime boundary because
        next_turn() is the public execution API.
        """

        if answer is None:
            raise ValueError(
                "An answer is required to continue "
                "the interview."
            )

        normalized = answer.strip()

        if not normalized:
            raise ValueError(
                "Interview answer cannot be empty."
            )

        return normalized

    # ==========================================================
    # Persistence
    # ==========================================================

    def _persist_new_turn(
        self,
        turn: ConversationTurn,
    ) -> None:
        """
        Append a newly-created conversation turn to the session.

        InterviewSession owns the conversation collection.

        No transaction is performed here. Transaction boundaries
        belong to the application/service persistence layer.
        """

        self.session.add_turn(
            turn
        )

    # ==========================================================
    # Session Navigation Synchronization
    # ==========================================================

    def _synchronize_session_navigation(
        self,
        turn: ConversationTurn,
    ) -> None:
        """
        Persist the navigation context represented by a turn.

        InterviewSession owns the persisted navigation context.

        Runtime does not select the goal or indicator. It only
        records the identities already selected by ConversationService.
        """

        goal_id = turn.goal_id
        indicator_id = turn.indicator_id

        # ------------------------------------------------------
        # Goal
        # ------------------------------------------------------

        if goal_id is None:
            self.session.set_current_goal(
                None
            )
        else:
            self.session.set_current_goal(
                goal_id
            )

        # ------------------------------------------------------
        # Indicator
        #
        # set_current_goal() intentionally clears the indicator.
        # Therefore indicator must be restored afterward.
        # ------------------------------------------------------

        if indicator_id is not None:
            self.session.set_current_indicator(
                indicator_id
            )

        # ------------------------------------------------------
        # Keep lightweight context aligned with the persisted
        # session state.
        # ------------------------------------------------------

        self.context.current_goal_id = (
            self.session.current_goal_id
        )

        self.context.current_indicator_id = (
            self.session.current_indicator_id
        )

    # ==========================================================
    # Runtime Context Synchronization
    # ==========================================================

    def _synchronize_context_after_answer(
        self,
        answer: str,
    ) -> None:
        """
        Update lightweight runtime answer bookkeeping.

        InterviewSession remains the persistent source of truth.

        AssessmentContext only receives runtime bookkeeping needed
        by the currently executing services.
        """

        add_answer = getattr(
            self.context,
            "add_answer",
            None,
        )

        if callable(add_answer):
            add_answer(
                answer
            )
            return

        # ------------------------------------------------------
        # Compatibility fallback.
        # ------------------------------------------------------

        self.context.last_answer = answer

        self.context.answers_received = (
            getattr(
                self.context,
                "answers_received",
                0,
            )
            + 1
        )

    def _synchronize_context_after_turn(
        self,
        *,
        turn: ConversationTurn,
        is_new_turn: bool,
    ) -> None:
        """
        Synchronize lightweight runtime context after a turn.

        Only a newly-created interviewer turn increments the
        question bookkeeping.

        A terminal reuse of the previous turn is not counted as
        another question.
        """

        # ------------------------------------------------------
        # Generated question
        # ------------------------------------------------------

        if (
            is_new_turn
            and turn.has_question
        ):
            add_question = getattr(
                self.context,
                "add_question",
                None,
            )

            if callable(add_question):
                add_question(
                    turn.question
                )
            else:
                # Compatibility fallback.
                self.context.current_question = (
                    turn.question
                )

                self.context.questions_asked = (
                    getattr(
                        self.context,
                        "questions_asked",
                        0,
                    )
                    + 1
                )

        # ------------------------------------------------------
        # Navigation
        #
        # Session is authoritative after synchronization.
        # ------------------------------------------------------

        self.context.current_goal_id = (
            self.session.current_goal_id
        )

        self.context.current_indicator_id = (
            self.session.current_indicator_id
        )

        # ------------------------------------------------------
        # Completion
        # ------------------------------------------------------

        self.context.interview_completed = bool(
            self.session.completed
            or turn.completed
        )

    # ==========================================================
    # Completion
    # ==========================================================

    def _synchronize_completion(
        self,
        turn: ConversationTurn,
    ) -> None:
        """
        Synchronize terminal turn state with InterviewSession.

        ConversationTurn.completed means:

            this conversation step terminates the interview.

        It does not mean that a goal was mastered.

        Goal mastery remains owned by GoalState / assessment logic.
        """

        # A terminal turn is the only conversation-level signal that
        # completes the interview. A newly-created non-terminal question
        # is the opposite signal: the interview is still active.
        #
        # This explicit lifecycle reconciliation prevents a stale
        # `session.completed=True` flag from being returned together with
        # a real next question (the Turn 10 protocol contradiction).
        InterviewLifecycle.synchronize_session(self.session, turn)
        self.context.interview_completed = bool(self.session.completed)

    # ==========================================================
    # Result
    # ==========================================================

    def build_result(self) -> Any:
        """
        Build the canonical AssessmentResult.

        Results are only available after interview completion.
        """

        if not self.session.completed:
            raise RuntimeError(
                "Interview has not completed."
            )

        return self.result_builder.build(
            self.session
        )

    # ==========================================================
    # Progress
    # ==========================================================

    def progress(self):
        """
        Return current interview progress.

        GoalManager remains responsible for progress calculation.
        """

        goal_manager = getattr(
            self.context,
            "goal_manager",
            None,
        )

        if goal_manager is None:
            return None

        progress = getattr(
            goal_manager,
            "progress",
            None,
        )

        if not callable(progress):
            return None

        return progress()

    # ==========================================================
    # Reset
    # ==========================================================

    def reset(self) -> None:
        """
        Reset the interview runtime.

        InterviewSession owns persistent reset semantics.

        AssessmentRuntime then resets only lightweight context
        bookkeeping.

        Runtime collaborators are preserved.
        """

        self.session.reset()

        self._reset_context()

    def _reset_context(self) -> None:
        """
        Reset lightweight AssessmentContext state.

        Persistent assessment state is NOT stored or independently
        reset here. GoalState objects belong to InterviewSession and
        are reset by InterviewSession.reset().
        """

        # ------------------------------------------------------
        # Navigation
        # ------------------------------------------------------

        self.context.current_goal_id = None
        self.context.current_indicator_id = None

        # ------------------------------------------------------
        # Lifecycle
        # ------------------------------------------------------

        self.context.interview_completed = False

        # ------------------------------------------------------
        # Conversation bookkeeping
        # ------------------------------------------------------

        self.context.current_question = None
        self.context.last_answer = None

        self.context.questions_asked = 0
        self.context.answers_received = 0
        self.context.completed_goals = 0

        # ------------------------------------------------------
        # Runtime conversation history
        # ------------------------------------------------------

        conversation_history = getattr(
            self.context,
            "conversation_history",
            None,
        )

        if isinstance(
            conversation_history,
            list,
        ):
            conversation_history.clear()

        # ------------------------------------------------------
        # Runtime evidence compatibility state
        #
        # Evidence that belongs to GoalState is NOT cleared here.
        # InterviewSession.reset() owns persistent assessment state.
        #
        # This only clears an optional legacy runtime evidence
        # collection if one exists.
        # ------------------------------------------------------

        evidence = getattr(
            self.context,
            "evidence",
            None,
        )

        if isinstance(
            evidence,
            list,
        ):
            evidence.clear()

