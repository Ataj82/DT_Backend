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

        knowledge_model = getattr(request.session, "knowledge_model", None)
        if knowledge_model is None:
            # Compatibility with legacy/injected retrievers that expose only
            # retrieve(indicator). Production sessions always carry a snapshot.
            context = self.knowledge_retriever.retrieve(request.indicator)
        else:
            context = self.knowledge_retriever.retrieve(
                request.indicator,
                knowledge_model=knowledge_model,
                language=(
                    (getattr(request.session, "metadata", {}) or {}).get("language")
                    or (getattr(request.interview_template, "metadata", {}) or {}).get("language")
                    or "en"
                ),
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
        # Persian-only output cleanup
        # ---------------------------------------------
        # The English generation path above is intentionally preserved.
        # Persian receives a small deterministic cleanup/quality gate because
        # some local multilingual models echo labels such as "سؤال:" or
        # explanatory meta-text instead of returning the requested utterance.
        from ..language.resolver import normalize_language
        from ..language.persian.text import (
            build_persian_repair_prompt,
            clean_persian_question,
            is_likely_persian_question,
            needs_persian_fluency_repair,
        )

        session_metadata = getattr(request.session, "metadata", {}) or {}
        language = normalize_language(
            session_metadata.get("language")
        )
        if language is None:
            language = normalize_language(
                (getattr(request.interview_template, "metadata", {}) or {}).get("language")
            ) or "en"
        if language == "fa":
            cleaned = clean_persian_question(question)
            if (
                not is_likely_persian_question(cleaned)
                or needs_persian_fluency_repair(cleaned)
            ):
                repaired = clean_persian_question(
                    self.llm.chat(
                        [
                            {
                                "role": "user",
                                "content": build_persian_repair_prompt(cleaned or question),
                            }
                        ]
                    )
                )
                if is_likely_persian_question(repaired):
                    cleaned = repaired
            question = cleaned or question.strip()
        else:
            # English is a closed output-language boundary. A multilingual
            # model may otherwise echo Persian source/context even though the
            # interview itself is configured as English.
            from ..language.english.text import (
                build_english_question_repair_prompt,
                clean_english_question,
                is_likely_english_text,
            )
            cleaned = clean_english_question(question)
            if not is_likely_english_text(cleaned):
                repaired = clean_english_question(
                    self.llm.chat(
                        [
                            {
                                "role": "user",
                                "content": build_english_question_repair_prompt(question),
                            }
                        ]
                    )
                )
                if is_likely_english_text(repaired):
                    cleaned = repaired
            question = cleaned or question.strip()
            if not is_likely_english_text(question):
                raise RuntimeError(
                    "English interview language contract violated: "
                    "question generation did not produce English output."
                )

        # ---------------------------------------------
        # Return DTO ----------------------------------

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