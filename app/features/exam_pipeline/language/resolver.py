"""Language resolution for interview sessions.

Precedence:
    teacher-selected interview language -> explicit KB language -> KB content detection -> English.

This module is intentionally independent from assessment/scoring/navigation logic.
"""
from __future__ import annotations

import re
from typing import Any

SUPPORTED_LANGUAGES = ("en", "fa", "ar")

_PERSIAN_CHARS = re.compile(r"[\u067e\u0686\u0698\u06af\u06cc\u06a9\u06d0\u06c0\u06c1\u06c2\u06c3\u06c4\u06c5\u06c6\u06c7\u06c8\u06c9\u06ca\u06cb\u06cc\u06cd\u06ce\u06cf\u06d0\u06d1\u06d2\u06d3\u06d4\u06d5\u06d6\u06d7\u06d8\u06d9\u06da\u06db\u06dc\u06dd\u06de\u06df\u06e0\u06e1\u06e2\u06e3\u06e4\u06e5\u06e6\u06e7\u06e8\u06e9\u06ea\u06eb\u06ec\u06ed\u06ee\u06ef\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u06fa\u06fb\u06fc\u06fd\u06fe\u06ff\u06a9\u06af\u067e\u0686\u0698]")
_PERSIAN_EXCLUSIVE = re.compile(r"[\u067e\u0686\u0698\u06af]")
_ARABIC_EXCLUSIVE = re.compile(r"[\u0629\u0649\u064a\u0643\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652]")
_ARABIC_RANGE = re.compile(r"[\u0600-\u06ff]")
_LATIN = re.compile(r"[A-Za-z]")


def normalize_language(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip().lower()
    aliases = {
        "en": "en", "eng": "en", "english": "en",
        "fa": "fa", "fas": "fa", "per": "fa", "persian": "fa", "farsi": "fa", "فارسی": "fa",
        "ar": "ar", "ara": "ar", "arabic": "ar", "العربية": "ar", "عربی": "ar",
    }
    return aliases.get(text, default)


def detect_text_language(text: str) -> str:
    """Conservative dominant-script detector; unknown/mixed content defaults to English."""
    text = str(text or "")
    fa = len(_PERSIAN_CHARS.findall(text))
    fa_excl = len(_PERSIAN_EXCLUSIVE.findall(text))
    ar_excl = len(_ARABIC_EXCLUSIVE.findall(text))
    ar = len(_ARABIC_RANGE.findall(text))
    latin = len(_LATIN.findall(text))

    if ar >= 8 and ar > latin * 1.5:
        # Distinguish Arabic from Persian:
        # Persian-specific letters (پ چ ژ گ) are decisive.
        if fa_excl > 0 or (fa >= 3 and fa >= max(3, latin // 3) and ar_excl == 0):
            return "fa"
        if ar_excl >= 2 or fa_excl == 0:
            return "ar"
        return "fa"

    if fa >= 3 and fa >= max(3, latin // 3):
        return "fa"

    return "en"


def detect_knowledge_language(knowledge: Any) -> str:
    """Infer language from explicit KB/document metadata or source content."""
    metadata = getattr(knowledge, "metadata", {}) or {}
    explicit = normalize_language(metadata.get("language"))
    if explicit:
        return explicit

    documents = list(getattr(knowledge, "documents", []) or [])
    explicit_docs = [normalize_language(getattr(d, "language", None)) for d in documents]
    explicit_docs = [x for x in explicit_docs if x]
    if explicit_docs and len(set(explicit_docs)) == 1 and explicit_docs[0] != "en":
        return explicit_docs[0]

    samples = []
    for doc in documents:
        content = str(getattr(doc, "content", "") or "")
        if content:
            samples.append(content[:12000])
    if samples:
        fa_count = sum(detect_text_language(s) == "fa" for s in samples)
        ar_count = sum(detect_text_language(s) == "ar" for s in samples)
        if fa_count > len(samples) / 2:
            return "fa"
        if ar_count > len(samples) / 2:
            return "ar"
    # Generated concepts can be useful when source documents are unavailable.
    labels = []
    for c in list(getattr(knowledge, "concepts", []) or []):
        labels.append(str(getattr(c, "name", "") or ""))
        labels.append(str(getattr(c, "definition", "") or ""))
    if labels:
        if sum(detect_text_language(x) == "fa" for x in labels) > len(labels) / 2:
            return "fa"
        if sum(detect_text_language(x) == "ar" for x in labels) > len(labels) / 2:
            return "ar"
    return "en"


def resolve_language(*, teacher_language: Any = None, knowledge: Any = None) -> tuple[str, str]:
    teacher = normalize_language(teacher_language)
    if teacher:
        return teacher, "teacher"
    kb_meta = getattr(knowledge, "metadata", {}) or {}
    kb_explicit = normalize_language(kb_meta.get("language"))
    if kb_explicit:
        return kb_explicit, "knowledge_base"
    return detect_knowledge_language(knowledge), "knowledge_detection"


def language_display_name(language: str) -> str:
    normalized = normalize_language(language)
    if normalized == "fa":
        return "Persian"
    if normalized == "ar":
        return "Arabic"
    return "English"
