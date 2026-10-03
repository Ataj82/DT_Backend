"""English-only output validation and repair helpers.

These helpers validate generated interviewer/evaluator prose. They never inspect
or reject the learner's answer merely because the learner used another language.
"""
from __future__ import annotations

import re

_NON_LATIN_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_CODE_FENCE_RE = re.compile(r"^```(?:text|markdown|plain|en|english)?\s*|\s*```$", re.IGNORECASE)
_META_PREFIX_RE = re.compile(
    r"^\s*(?:in\s+english|english\s+answer|english\s+feedback|"
    r"feedback|rationale|question)\s*[:：-]\s*",
    re.IGNORECASE,
)


def contains_non_latin_script(text: str) -> bool:
    return bool(_NON_LATIN_SCRIPT_RE.search(str(text or "")))


def is_likely_english_text(text: str, *, allow_empty: bool = False) -> bool:
    value = str(text or "").strip()
    if not value:
        return allow_empty
    if contains_non_latin_script(value):
        return False
    # Require at least one Latin letter for natural-language output. Numeric
    # scores, identifiers, or punctuation alone are not learner-facing prose.
    return bool(re.search(r"[A-Za-z]", value))


def clean_english_question(text: str) -> str:
    value = str(text or "").strip()
    value = _CODE_FENCE_RE.sub("", value).strip()
    value = _META_PREFIX_RE.sub("", value, count=1).strip()
    return re.sub(r"\s+", " ", value).strip()


def build_english_question_repair_prompt(question: str) -> str:
    return f"""
Rewrite the raw model output below as exactly one natural, student-facing oral
interview question in English.

STRICT LANGUAGE CONTRACT:
- Output English only.
- Do not use Persian, Arabic, or any other non-Latin-script prose.
- Preserve technical identifiers such as Python, def, return, API, and SQL.
- Preserve the original assessment intent and do not add new content.
- Do not translate the learner's answer or invent an answer.
- Do not add "Question:", "In English:", explanations, Markdown, or code fences.
- Return only the question.

RAW OUTPUT:
{question}
""".strip()
