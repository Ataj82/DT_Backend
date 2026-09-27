"""
assessment/session_manager.py

Coordinates the lifecycle of an interview session.

This service is responsible for loading runtime state,
executing one conversational turn, and persisting the
updated state.
"""

from __future__ import annotations

from ..conversation.models import ConversationTurn


class AssessmentSessionManager:

    def __init__(
        self,
        *,
        session_repository,
        runtime_repository,
        runtime_factory,
        unit_of_work,
    ):

        self.session_repository = session_repository

        self.runtime_repository = runtime_repository

        self.runtime_factory = runtime_factory

        self.unit_of_work = unit_of_work

    # ---------------------------------------------------------
    # Session
    # ---------------------------------------------------------

    def create_runtime(
        self,
        session_id: str,
    ):
        """
        Creates a brand-new runtime for a session.
        """

        session = self.session_repository.get(session_id)

        if session is None:
            raise ValueError(
                f"Unknown session '{session_id}'."
            )

        runtime = self.runtime_factory.create(
            session
        )

        self.runtime_repository.save(
            runtime.context
        )

        return runtime

    # ---------------------------------------------------------
    # Conversation
    # ---------------------------------------------------------

    def next_turn(
        self,
        session_id: str,
        answer: str | None = None,
    ) -> ConversationTurn:
        """
        Executes one interview turn.
        """

        with self.unit_of_work:

            context = self.runtime_repository.load(
                session_id
            )

            if context is None:

                runtime = self.create_runtime(
                    session_id
                )

            else:

                runtime = (
                    self.runtime_factory
                    .create_from_context(
                        context
                    )
                )

            turn = runtime.next_turn(
                answer
            )

            self.runtime_repository.save(
                runtime.context
            )

            self.unit_of_work.commit()

            return turn

    # ---------------------------------------------------------
    # Result
    # ---------------------------------------------------------

    def build_result(
        self,
        session_id: str,
    ):

        context = self.runtime_repository.load(
            session_id
        )

        if context is None:

            raise ValueError(
                "Interview runtime not found."
            )

        runtime = (
            self.runtime_factory
            .create_from_context(
                context
            )
        )

        return runtime.build_result()

    # ---------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------

    def reset(
        self,
        session_id: str,
    ):

        context = self.runtime_repository.load(
            session_id
        )

        if context is None:
            return

        context.reset()

        self.runtime_repository.save(
            context
        )

    def delete(
        self,
        session_id: str,
    ):

        self.runtime_repository.delete(
            session_id
        )

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return self.runtime_repository.exists(
            session_id
        )