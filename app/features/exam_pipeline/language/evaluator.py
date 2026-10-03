"""Route answer evaluation through a strict language-specific boundary."""
from __future__ import annotations

from .resolver import normalize_language
from .english.evaluation import EnglishAnswerEvaluator
from .persian.evaluation import PersianAnswerEvaluator


class LanguageAwareAnswerEvaluator:
    def __init__(self, llm, english=None, persian=None):
        self.english = english or EnglishAnswerEvaluator(llm=llm)
        self.persian = persian or PersianAnswerEvaluator(llm=llm)

    def evaluate(self, *, language="en", **kwargs):
        normalized = normalize_language(language, default="en")
        if normalized == "fa":
            return self.persian.evaluate(**kwargs)
        return self.english.evaluate(**kwargs)
