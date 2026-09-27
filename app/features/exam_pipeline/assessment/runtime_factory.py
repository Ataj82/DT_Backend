"""
app/assessment/runtime_factory.py

Factory responsible for constructing an AssessmentRuntime for one
InterviewSession.
"""

from __future__ import annotations

from ..assessment.context_factory import (
    AssessmentContextFactory,
)
from ..assessment.result_builder import (
    AssessmentResultBuilder,
)
from ..assessment.runtime import (
    AssessmentRuntime,
)
from ..conversation.service import (
    ConversationService,
)


class AssessmentRuntimeFactory:
    """
    Reconstruct a complete runtime for one persistent interview session.
    """

    def __init__(
        self,
        *,
        context_factory: AssessmentContextFactory,
        result_builder: AssessmentResultBuilder,
        evaluation_service,
        difficulty_controller=None,
        abet_service=None,
    ) -> None:

        self.context_factory = (
            context_factory
        )

        self.result_builder = (
            result_builder
        )

        self.evaluation_service = (
            evaluation_service
        )

        self.difficulty_controller = difficulty_controller
        self.abet_service = abet_service

    # ==========================================================
    # Public API
    # ==========================================================

    def create(
        self,
        *,
        session,
    ) -> AssessmentRuntime:

        if session is None:
            raise ValueError(
                "Cannot create an assessment runtime "
                "without a session."
            )

        if self.evaluation_service is None:
            raise RuntimeError(
                "AssessmentRuntimeFactory requires "
                "an evaluation_service."
            )

        # ------------------------------------------------------
        # Build session-scoped context.
        # ------------------------------------------------------

        context = (
            self.context_factory.create(
                session=session,
            )
        )

        if context is None:
            raise RuntimeError(
                "AssessmentContextFactory returned no context."
            )

        # ------------------------------------------------------
        # Resolve navigator.
        # ------------------------------------------------------

        navigator = getattr(
            context,
            "navigator",
            None,
        )

        if navigator is None:
            raise RuntimeError(
                "AssessmentContext does not provide "
                "a navigator."
            )

        # ------------------------------------------------------
        # Resolve question generator.
        # ------------------------------------------------------

        question_generator = getattr(
            context,
            "question_generator",
            None,
        )

        if question_generator is None:
            raise RuntimeError(
                "AssessmentContext does not provide "
                "a question_generator."
            )

        # ------------------------------------------------------
        # Construct conversation service.
        # ------------------------------------------------------

        conversation_service = (
            ConversationService(
                evaluation_service=(
                    self.evaluation_service
                ),
                navigator=navigator,
                question_generator=(
                    question_generator
                ),
                difficulty_controller=(
                    self.difficulty_controller
                ),
                abet_service=self.abet_service,
            )
        )

        # ------------------------------------------------------
        # Construct runtime.
        # ------------------------------------------------------

        return AssessmentRuntime(
            session=session,
            context=context,
            conversation_service=(
                conversation_service
            ),
            result_builder=(
                self.result_builder
            ),
        )