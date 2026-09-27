"""
interview/question_generator.py

Stateless Question Generator.

Responsibilities
----------------
• Retrieve knowledge
• Build the interview prompt
• Invoke the LLM
• Return a GeneratedQuestion

This service owns NO runtime interview state.

Question history is obtained from InterviewSession.
"""

from __future__ import annotations

from .generated_question import GeneratedQuestion
from .question_request import QuestionRequest
from ..interview.prompt_builder import (
    QuestionPromptBuilder,
)
from ..interview.knowledge_retriever import (
    KnowledgeRetriever,
)

class QuestionGenerator:
    """
    Stateless application service responsible for generating
    one interview question.
    """

    def __init__(
        self,
        *,
        llm,
        knowledge_retriever,
        prompt_builder,
    ):
        self.llm = llm
        self.knowledge_retriever = knowledge_retriever
        self.prompt_builder = prompt_builder

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def generate(
        self,
        request: QuestionRequest,
    ) -> GeneratedQuestion:
        """
        Generate exactly one interview question.
        """

        # ---------------------------------------------
        # Retrieve supporting knowledge
        # ---------------------------------------------

        context = self.knowledge_retriever.retrieve(
            request.indicator
        )

        # ---------------------------------------------
        # Extract previous questions from session
        # ---------------------------------------------

        history = self._question_history(
            request.session
        )

        # ---------------------------------------------
        # Build prompt
        # ---------------------------------------------

        prompt = self.prompt_builder.build(
            request=request,
            context=context,
            history=history,
        )

        # ---------------------------------------------
        # Ask LLM
        # ---------------------------------------------

        question = self.llm.chat(
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        )

        # ---------------------------------------------
        # Return DTO
        # ---------------------------------------------

        return GeneratedQuestion(
            question=question,
            context=context,
            indicator_id=request.indicator.id,
            difficulty=request.difficulty,
            difficulty_reason=request.difficulty_reason,
        )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _question_history(
        session,
        limit: int = 3,
    ) -> str:
        """
        Extract recent interviewer questions from the session.
        """

        questions = [
            turn.question
            for turn in session.turns
            if turn.question
        ][-limit:]

        if not questions:
            return "None"

        return "\n".join(
            f"{i + 1}. {question}"
            for i, question in enumerate(questions)
        )