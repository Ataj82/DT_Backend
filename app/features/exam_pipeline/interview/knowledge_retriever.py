"""
interview/knowledge_retriever.py

Retrieves bounded supporting knowledge for question generation.

The LLM used by the application has a small context window. Retrieval
therefore returns a compact, deterministic context instead of passing an
entire source document into every question-generation prompt.
"""

from __future__ import annotations


class KnowledgeRetriever:
    """Adapt the knowledge repository to question-generation needs."""

    # Keep enough context for grounding while leaving room for the
    # goal, indicator, history, instructions, and the model response.
    DEFAULT_MAX_CONTEXT_CHARS = 3500

    def __init__(
        self,
        *,
        knowledge_repository,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ):
        if max_context_chars < 500:
            raise ValueError("max_context_chars must be at least 500.")

        self.knowledge_repository = knowledge_repository
        self.max_context_chars = max_context_chars

    def retrieve(
        self,
        indicator,
        *,
        knowledge_model=None,
        language: str | None = None,
    ) -> str:
        """Return bounded supporting knowledge for the selected interview scope.

        ``knowledge_model`` and ``language`` are optional for compatibility
        with older injected repositories/tests. Production interview sessions
        pass both so retrieval cannot cross knowledge-base or language
        boundaries.
        """
        if knowledge_model is None:
            context = self.knowledge_repository.retrieve(indicator)
        else:
            context = self.knowledge_repository.retrieve(
                indicator,
                knowledge_model=knowledge_model,
                language=language,
            )

        if not isinstance(context, str):
            context = str(context)

        context = context.strip()
        if not context:
            return "None"

        if len(context) <= self.max_context_chars:
            return context

        # Prefer complete lines/paragraphs over cutting a sentence in half.
        boundary = context.rfind("\n", 0, self.max_context_chars)
        if boundary < self.max_context_chars // 2:
            boundary = context.rfind(" ", 0, self.max_context_chars)
        if boundary < self.max_context_chars // 2:
            boundary = self.max_context_chars

        return (
            context[:boundary].rstrip()
            + "\n[Knowledge context truncated for model context limits.]"
        )
