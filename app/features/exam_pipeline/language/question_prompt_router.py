"""Select the language-specific question prompt without changing English behavior."""
from __future__ import annotations
from .resolver import normalize_language
from .persian.question_prompt import PersianQuestionPromptBuilder
from ..interview.prompt_builder import QuestionPromptBuilder


class LanguageAwareQuestionPromptBuilder:
    def __init__(self, english=None, persian=None):
        self.english = english or QuestionPromptBuilder()
        self.persian = persian or PersianQuestionPromptBuilder()

    def build(self, request, context, history):
        # Session metadata is the authoritative language boundary. The
        # interview template is a compatibility fallback, not a higher-priority
        # source, because a stale template may still carry ``en`` after a
        # Persian session has been created.
        session_metadata = getattr(getattr(request, "session", None), "metadata", {}) or {}
        language = normalize_language(session_metadata.get("language"))
        if language is None:
            language = normalize_language(
                (getattr(request.interview_template, "metadata", {}) or {}).get("language")
            ) or "en"
        if language == "fa":
            return self.persian.build(request, context, history)
        return self.english.build(request, context, history)
