"""
app/assessment/context_factory.py

Factory responsible for constructing an AssessmentContext for one
interview session.

The factory creates session-scoped runtime collaborators and wires
them together.

Responsibilities
----------------
- validate the persistent InterviewSession
- validate required application dependencies
- create GoalManager
- create InterviewNavigator
- create InterviewerStrategy
- assemble AssessmentContext
- restore runtime state from InterviewSession

The factory does NOT:
- evaluate learner answers
- calculate assessment metrics
- generate questions
- persist sessions
- advance goals as business logic
- modify assessment evidence

Architecture
------------
InterviewSession is the persistent source of truth.

AssessmentContext is transient runtime state reconstructed from
InterviewSession.

AssessmentRuntimeFactory / ConversationService own runtime
orchestration. This factory only performs composition and state
restoration.
"""

from __future__ import annotations

from typing import Any

from ..assessment.goal_manager import GoalManager
from ..assessment.result_builder import AssessmentResultBuilder
from ..interview.context import AssessmentContext
from ..navigation.interview_navigator import InterviewNavigator
from ..strategies.interviewer_strategy import InterviewerStrategy


class AssessmentContextFactory:
    """
    Construct the complete runtime context for one interview session.

    Application-wide collaborators are injected through the
    constructor.

    Session-specific collaborators are created inside ``create()``.

    The factory itself contains no assessment or navigation business
    rules.
    """

    def __init__(
        self,
        *,
        coverage_engine,
        evidence_planner,
        progress_reasoner,
        question_generator,
        result_builder: AssessmentResultBuilder,
        abet_service=None,
    ) -> None:

        self.coverage_engine = coverage_engine
        self.evidence_planner = evidence_planner
        self.progress_reasoner = progress_reasoner
        self.question_generator = question_generator
        self.result_builder = result_builder
        self.abet_service = abet_service

    # ==========================================================
    # Public API
    # ==========================================================

    def create(
        self,
        *,
        session,
    ) -> AssessmentContext:
        """
        Reconstruct the runtime context for ``session``.

        ``InterviewSession`` remains the persistent source of truth.

        Every object created in this method is runtime-scoped and may
        safely be reconstructed when an interview resumes.

        No persistence operation is performed here.
        """

        self._validate_session(
            session
        )

        self._validate_dependencies()

        # ------------------------------------------------------
        # Goal manager
        #
        # GoalManager operates over the persistent InterviewSession
        # goal state.
        # ------------------------------------------------------

        goal_manager = GoalManager(
            session
        )

        # ------------------------------------------------------
        # Navigator
        #
        # Navigator owns goal/indicator navigation.
        # Evidence selection remains delegated to EvidencePlanner.
        # ------------------------------------------------------

        navigator = InterviewNavigator(
            goal_manager=goal_manager,
            evidence_planner=self.evidence_planner,
        )

        # ------------------------------------------------------
        # Strategy
        #
        # Strategy is session-scoped.
        #
        # The current codebase has one concrete InterviewerStrategy,
        # so preserve that behavior while keeping construction
        # isolated here for future strategy selection.
        # ------------------------------------------------------

        strategy = self._create_strategy(
            session
        )

        # ------------------------------------------------------
        # Runtime context
        #
        # AssessmentEngine intentionally does not belong here.
        #
        # AssessmentRuntimeFactory owns the application-level
        # AssessmentEngine and injects it into ConversationService.
        # ------------------------------------------------------

        context = AssessmentContext(
            session=session,
            configuration=getattr(
                session,
                "configuration",
                None,
            ),
            student_id=session.student_id,
            knowledge_model=session.knowledge_model,
            goal_model=session.goal_model,
            goal_manager=goal_manager,
            navigator=navigator,
            strategy=strategy,
            coverage_engine=self.coverage_engine,
            evidence_planner=self.evidence_planner,
            progress_reasoner=self.progress_reasoner,
            question_generator=self.question_generator,
            result_builder=self.result_builder,
            abet_service=self.abet_service,
        )

        # ------------------------------------------------------
        # Restore runtime state.
        #
        # This is reconstruction only. No new assessment decisions,
        # navigation decisions, or persistence operations occur.
        # ------------------------------------------------------

        self._restore_runtime_state(
            context
        )

        return context

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _validate_session(
        session,
    ) -> None:
        """
        Validate the minimum persistent state required to construct
        a functioning runtime.

        Validation is intentionally limited to state actually
        required by this factory.
        """

        if session is None:
            raise ValueError(
                "Cannot create an assessment context "
                "without a session."
            )

        if not getattr(
            session,
            "student_id",
            None,
        ):
            raise ValueError(
                "Interview session has no student_id."
            )

        if getattr(
            session,
            "knowledge_model",
            None,
        ) is None:
            raise ValueError(
                "Interview session has no knowledge model."
            )

        if getattr(
            session,
            "goal_model",
            None,
        ) is None:
            raise ValueError(
                "Interview session has no goal model."
            )

    def _validate_dependencies(
        self,
    ) -> None:
        """
        Fail fast when the application has been composed without
        required runtime dependencies.
        """

        required = (
            (
                "coverage_engine",
                self.coverage_engine,
            ),
            (
                "evidence_planner",
                self.evidence_planner,
            ),
            (
                "progress_reasoner",
                self.progress_reasoner,
            ),
            (
                "question_generator",
                self.question_generator,
            ),
            (
                "result_builder",
                self.result_builder,
            ),
        )

        missing = [
            name
            for name, dependency in required
            if dependency is None
        ]

        if not missing:
            return

        raise RuntimeError(
            "AssessmentContextFactory is missing required "
            "dependencies: "
            + ", ".join(missing)
            + "."
        )

    # ==========================================================
    # Strategy
    # ==========================================================

    @staticmethod
    def _create_strategy(
        session,
    ) -> InterviewerStrategy:
        """
        Create the interviewer strategy for the session.

        The current application exposes a strategy configuration
        value but only provides one concrete InterviewerStrategy.

        Therefore the existing behavior is preserved.

        Keeping this method isolated allows future strategy
        implementations to be selected here without changing
        AssessmentRuntime or ConversationService.
        """

        # Read the configuration deliberately so this remains the
        # designated strategy-selection boundary.
        configuration = getattr(
            session,
            "configuration",
            None,
        )

        _strategy_type = getattr(
            configuration,
            "strategy",
            None,
        )

        # Current supported implementation.
        return InterviewerStrategy()

    # ==========================================================
    # Runtime State Restoration
    # ==========================================================

    @classmethod
    def _restore_runtime_state(
        cls,
        context: AssessmentContext,
    ) -> None:
        """
        Restore transient AssessmentContext state from the
        persistent InterviewSession.

        Persistent state remains owned by InterviewSession.

        This method only reconstructs the runtime representation.

        It does not:
        - evaluate answers
        - select new goals
        - select new indicators
        - generate questions
        - modify evidence
        - persist anything
        """

        session = context.session

        # ------------------------------------------------------
        # Lifecycle
        # ------------------------------------------------------

        if getattr(
            session,
            "completed",
            False,
        ):
            context.mark_completed()

        # ------------------------------------------------------
        # Navigation position
        # ------------------------------------------------------

        cls._restore_navigation_state(
            context
        )

        # ------------------------------------------------------
        # Conversation bookkeeping
        # ------------------------------------------------------

        cls._restore_conversation_state(
            context
        )

    @staticmethod
    def _restore_navigation_state(
        context: AssessmentContext,
    ) -> None:
        """
        Restore current goal/indicator identifiers.

        GoalManager remains responsible for determining the current
        goal. The factory only mirrors that runtime position into
        AssessmentContext.

        The current indicator comes from the current GoalState.
        """

        goal_manager = context.goal_manager

        if goal_manager is None:
            return

        goal = getattr(
            goal_manager,
            "current_goal",
            None,
        )

        if goal is None:
            return

        goal_id = getattr(
            goal,
            "id",
            None,
        )

        if goal_id is not None:
            context.current_goal_id = goal_id

        goal_state = getattr(
            goal_manager,
            "current_goal_state",
            None,
        )

        if goal_state is None:
            return

        indicator_id = getattr(
            goal_state,
            "current_indicator_id",
            None,
        )

        if indicator_id is not None:
            context.current_indicator_id = (
                indicator_id
            )
        session = context.session

        session_goal_id = getattr(
            session,
            "current_goal_id",
            None,
        )

        session_indicator_id = getattr(
            session,
            "current_indicator_id",
            None,
        )

        if session_goal_id is not None:
            context.current_goal_id = session_goal_id

        if session_indicator_id is not None:
            context.current_indicator_id = session_indicator_id

    @staticmethod
    def _restore_conversation_state(
        context: AssessmentContext,
    ) -> None:
        """
        Reconstruct lightweight runtime conversation state from
        persisted InterviewSession turns.

        InterviewSession remains authoritative.

        The context receives only derived runtime bookkeeping:

        - questions_asked
        - answers_received
        - current_question
        - last_answer
        - conversation_history
        """

        session = context.session

        turns = getattr(
            session,
            "turns",
            None,
        )

        if not turns:
            return

        questions_asked = 0
        answers_received = 0

        current_question: str | None = None
        last_answer: str | None = None

        conversation_history = context.conversation_history

        # ------------------------------------------------------
        # Rebuild only from persisted ConversationTurn objects.
        #
        # No assessment computation is performed here.
        # ------------------------------------------------------

        for turn in turns:

            question = getattr(
                turn,
                "question",
                "",
            )

            answer = getattr(
                turn,
                "answer",
                "",
            )

            if question:
                questions_asked += 1

                current_question = (
                    question
                )

                conversation_history.append(
                    {
                        "role": "assistant",
                        "content": question,
                    }
                )

            if answer:
                answers_received += 1

                last_answer = answer

                conversation_history.append(
                    {
                        "role": "user",
                        "content": answer,
                    }
                )

        # ------------------------------------------------------
        # Publish derived runtime counters.
        # ------------------------------------------------------

        context.questions_asked = (
            questions_asked
        )

        context.answers_received = (
            answers_received
        )

        context.current_question = (
            current_question
        )

        context.last_answer = (
            last_answer
        )

        # ------------------------------------------------------
        # Completion state remains session-authoritative.
        # ------------------------------------------------------

        context.interview_completed = bool(
            session.completed
        )

    # ==========================================================
    # Dependency Accessors
    # ==========================================================

    @property
    def has_required_dependencies(
        self,
    ) -> bool:
        """
        Return whether all required runtime dependencies are
        available.
        """

        return all(
            dependency is not None
            for dependency in (
                self.coverage_engine,
                self.evidence_planner,
                self.progress_reasoner,
                self.question_generator,
                self.result_builder,
            )
        )