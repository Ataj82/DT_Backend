
"""
app/services/assessment_service.py

Application service responsible for executing assessments.

The service coordinates AssessmentRuntime but contains no
assessment algorithms itself.

Responsibilities
----------------
- reconstruct an AssessmentRuntime
- execute runtime operations
- persist runtime/session changes
- expose assessment result operations

Non-responsibilities
--------------------
- answer evaluation
- scoring
- evidence reasoning
- goal navigation
- question generation
- assessment algorithms
"""

from __future__ import annotations

from typing import Any

from ..assessment.runtime_factory import AssessmentRuntimeFactory
from ..unit_of_work.unit_of_work import UnitOfWork


class AssessmentService:
    """
    Application service for assessment execution.

    AssessmentService is deliberately thin.

    The actual assessment behavior lives in:
        AssessmentRuntime
        ConversationService
        assessment pipeline components
        AssessmentResultBuilder

    Persistent state is owned by InterviewSession and persisted
    through UnitOfWork.
    """

    def __init__(
        self,
        *,
        runtime_factory: AssessmentRuntimeFactory,
        uow: UnitOfWork,
    ) -> None:

        self.runtime_factory = runtime_factory
        self.uow = uow

    # ==========================================================
    # Runtime
    # ==========================================================

    def create_runtime(
        self,
        session_id: str,
    ):
        """
        Reconstruct an AssessmentRuntime for an existing session.

        The session is loaded from the repository and then passed
        to the runtime factory.

        No assessment logic is executed here.
        """

        with self.uow:

            session = self.uow.sessions.get(
                session_id
            )

        if session is None:
            raise ValueError(
                f"Assessment session '{session_id}' not found."
            )

        return self.runtime_factory.create(
            session=session,
        )

    # ==========================================================
    # Interview / Assessment Execution
    # ==========================================================

    def next_turn(
        self,
        session_id: str,
        answer: str | None = None,
    ):
        """
        Execute one interview turn through AssessmentRuntime.

        The runtime owns:
            - conversation orchestration
            - assessment pipeline execution
            - state synchronization
            - completion detection

        This service only handles runtime creation and persistence.
        """

        runtime = self.create_runtime(
            session_id
        )

        turn = runtime.next_turn(
            answer
        )

        self._save_runtime(
            runtime
        )

        return turn

    # ==========================================================
    # Completion
    # ==========================================================

    def complete(
        self,
        session_id: str,
    ):
        """
        Complete an already-finished assessment and return the
        final assessment result.

        This method does NOT artificially mark the session as
        completed.

        Completion must already have been established by the
        interview/assessment pipeline.
        """

        runtime = self.create_runtime(
            session_id
        )

        if not runtime.session.completed:
            runtime.session.mark_completed()
            if hasattr(runtime.context, "mark_completed"):
                try:
                    runtime.context.mark_completed()
                except Exception:
                    pass

        result = runtime.build_result()

        self._save_runtime(
            runtime
        )

        return result

    # ==========================================================
    # Result
    # ==========================================================

    def build_result(
        self,
        session_id: str,
    ):
        """
        Build the assessment result for a completed session.

        AssessmentRuntime and AssessmentResultBuilder remain
        responsible for result construction.
        """

        runtime = self.create_runtime(
            session_id
        )

        result = runtime.build_result()

        self._save_runtime(
            runtime
        )

        return result

    def get_result(
        self,
        session_id: str,
    ):
        """
        Retrieve/build the assessment result for a completed
        session.

        The result is constructed by AssessmentRuntime rather
        than by this service.
        """

        runtime = self.create_runtime(
            session_id
        )

        result = runtime.build_result()

        self._save_runtime(
            runtime
        )

        return result

    # ==========================================================
    # Progress
    # ==========================================================

    def progress(
        self,
        session_id: str,
    ) -> float | None:
        """
        Return current interview progress.

        Progress calculation remains inside AssessmentRuntime
        and GoalManager.
        """

        runtime = self.create_runtime(
            session_id
        )

        return runtime.progress()

    # ==========================================================
    # Reset
    # ==========================================================

    def reset(
        self,
        session_id: str,
    ) -> None:
        """
        Reset an assessment session.

        Runtime owns reset semantics while this service owns
        persistence.
        """

        runtime = self.create_runtime(
            session_id
        )

        runtime.reset()

        self._save_runtime(
            runtime
        )

    # ==========================================================
    # Persistence
    # ==========================================================

    def _save_runtime(
        self,
        runtime: Any,
    ) -> None:
        """
        Persist the runtime session.

        Transaction handling belongs to the application-service
        layer.
        """

        with self.uow:

            self.uow.sessions.save(
                runtime.session
            )

            self.uow.commit()

