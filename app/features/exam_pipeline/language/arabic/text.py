"""Arabic language text normalization and helper functions."""
from __future__ import annotations

import re

# Model prefixes and wrappers
_QUESTION_PREFIX_RE = re.compile(
    r"^(?:\s*(?:\*\*)?(?:سؤال|السؤال|سؤال شفهي|question)(?:\*\*)?\s*[:：-]\s*)+",
    flags=re.IGNORECASE,
)
_META_PREFIX_RE = re.compile(
    r"^\s*(?:باللغة\s+العربية|في\s+اللغة\s+العربية|إجابة\s+عربية|المخرجات\s+بالعربية|رد\s+بالعربية)"
    r"(?:[^:：\n]*[:：]\s*)",
    flags=re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"^```(?:text|markdown|plain|ar|arabic)?\s*|\s*```$", re.IGNORECASE)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_LATIN_TOKEN_RE = re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9_.+#/-]*(?![A-Za-z])")
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06ff]")


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_arabic_concept(label: str) -> str:
    """Return a readable Arabic concept phrase while preserving identifiers."""
    text = _clean_space(str(label or "")).strip(" .،؛:")
    if not text:
        return "المفهوم المطلوب"

    def quote_token(match: re.Match[str]) -> str:
        token = match.group(0)
        return f"«{token}»"

    text = _LATIN_TOKEN_RE.sub(quote_token, text)
    return text


_COMMON_ARABIC_CONCEPTS = {
    "python": "بايثون",
    "python functions": "دوال بايثون",
    "functions": "الدوال",
    "function": "الدالة",
    "python variables": "متغيرات بايثون",
    "variables": "المتغيرات",
    "variable": "المتغير",
    "loop": "حلقة التكرار",
    "loops": "حلقات التكرار",
    "conditional": "الجمل الشرطية",
    "conditionals": "الجمل الشرطية",
    "class": "الفئة (Class)",
    "classes": "الفئات (Classes)",
    "object": "الكائن (Object)",
    "objects": "الكائنات (Objects)",
    "list": "القائمة",
    "lists": "القوائم",
    "dictionary": "القاموس",
    "dictionaries": "القواميس",
    "exception": "الاستثناء",
    "exceptions": "الاستثناءات",
    "recursion": "العودية (Recursion)",
    "scope": "نطاق المتغيرات",
}

_TECHNICAL_KEYWORDS = {
    "def": "الكلمة المفتاحية «def» في بايثون",
    "return": "الأمر «return» في بايثون",
    "class": "الفئة «class» في بايثون",
    "import": "أمر الاستيراد «import» في بايثون",
}


def _arabic_concept_phrase(label: str) -> str:
    text = _clean_space(str(label or "")).strip(" .،؛:")
    if not text:
        return "المفهوم المطلوب"

    key = text.casefold()
    if key in _TECHNICAL_KEYWORDS:
        return _TECHNICAL_KEYWORDS[key]
    if key in _COMMON_ARABIC_CONCEPTS:
        return _COMMON_ARABIC_CONCEPTS[key]

    normalized = key.replace("_", " ")
    if normalized in _COMMON_ARABIC_CONCEPTS:
        return _COMMON_ARABIC_CONCEPTS[normalized]

    return format_arabic_concept(text)


def build_arabic_goal_title(label: str) -> str:
    concept = _arabic_concept_phrase(label)
    if concept.startswith("الكلمة المفتاحية «") or concept.startswith("الأمر «"):
        return f"استيعاب استخدام {concept}"
    if concept in {"دوال بايثون", "متغيرات بايثون", "الجمل الشرطية"}:
        return f"استيعاب {concept}"
    if concept == "بايثون":
        return "استيعاب المفاهيم الأساسية لبايثون"
    return f"استيعاب مفهوم {concept}"


def build_arabic_goal_description(label: str, description: str | None) -> str:
    source = _clean_space(str(description or "")).strip(" .،؛:")
    concept = _arabic_concept_phrase(label)

    if source and len(_ARABIC_LETTER_RE.findall(source)) >= 5:
        return f"يجب أن يكون المتعلم قادراً على شرح {source} وتوضيح كيفية تطبيقه في سياق عملي."

    if concept.startswith("الكلمة المفتاحية «") or concept.startswith("الأمر «"):
        return f"يجب أن يكون المتعلم قادراً على شرح استخدام {concept} وتقديم مثال تطبيقي بسيط."
    if concept in {"دوال بايثون", "متغيرات بايثون", "الجمل الشرطية"}:
        return f"يجب أن يكون المتعلم قادراً على شرح {concept} وتطبيقها عملياً."
    if concept == "بايثون":
        return "يجب أن يكون المتعلم قادراً على شرح المفاهيم الأساسية للغة بايثون وتوضيح تطبيقاتها."
    return f"يجب أن يكون المتعلم قادراً على شرح مفهوم {concept} وتوضيح كيفية استخدامه عملياً."


def build_arabic_fallback_questions(topic: str) -> list[str]:
    raw = _clean_space(str(topic or "")).strip(" .،؛:") or "الموضوع المطلوب"
    key = raw.casefold()
    concept = _TECHNICAL_KEYWORDS.get(key) or _COMMON_ARABIC_CONCEPTS.get(key)
    if concept is None:
        concept = _COMMON_ARABIC_CONCEPTS.get(key.replace("_", " "))
    if concept is None:
        concept = format_arabic_concept(raw)
    return [
        f"ما هو مفهوم {concept} وما أهم استخداماته؟ اذكر مثالاً توضيحياً بسيطاً.",
        f"إذا أردت تطبيق {concept} في حل مسألة برمجية أو تقنية عملية، من أين تبدأ وكيف تتأكد من صحة النتيجة؟",
        f"اذكر مثالاً محدداً على {concept} واشرح كيف تتحقق من أن الحل سليم وخالٍ من الأخطاء.",
        f"اشرح {concept} بأسلوبك الخاص، وبين في أي السيناريوهات يكون استخدامه هو الخيار الأنسب.",
    ]


def clean_arabic_question(text: str) -> str:
    """Remove common LLM meta-wrappers while preserving the generated Arabic question."""
    value = str(text or "").strip()
    value = _CODE_FENCE_RE.sub("", value).strip()
    value = _MARKDOWN_BOLD_RE.sub(r"\1", value).strip()
    value = _INLINE_CODE_RE.sub(r"\1", value).strip()

    value = _META_PREFIX_RE.sub("", value, count=1).strip()

    match = re.search(r"(?:^|\n)\s*(?:سؤال|السؤال|سؤال شفهي|question)\s*[:：-]\s*", value, flags=re.IGNORECASE)
    if match:
        value = value[match.end():].strip()
    else:
        near_start = re.search(r"(?:سؤال|السؤال|سؤال شفهي|question)\s*[:：-]\s*", value[:120], flags=re.IGNORECASE)
        if near_start:
            value = value[near_start.end():].strip()
        else:
            value = _QUESTION_PREFIX_RE.sub("", value).strip()

    if "؟" in value:
        first_q = value.find("؟")
        candidate = value[: first_q + 1].strip()
        if _ARABIC_LETTER_RE.search(candidate):
            value = candidate
    elif "?" in value:
        first_q = value.find("?")
        candidate = value[: first_q + 1].strip()
        if _ARABIC_LETTER_RE.search(candidate):
            value = candidate

    return _clean_space(value)


def is_likely_arabic_question(text: str) -> bool:
    """Conservative quality gate used only for Arabic question generation."""
    value = clean_arabic_question(text)
    if len(value) < 8 or not _ARABIC_LETTER_RE.search(value):
        return False
    if "؟" in value or "?" in value:
        return True
    return bool(re.match(r"^(?:لماذا|كيف|ما|ماذا|هل|أي|في\s+أي|برأيك|إذا|لو|اذكر|اشرح|وضح)", value))


_ARABIC_AWKWARD_PATTERNS = (
    re.compile(r"\bمفهوم\s+(?:def|return|class|import)\b.*?ما فائدته", re.IGNORECASE),
    re.compile(r"هل\s+يمكنك\s+ذكر\s+مثال\s+بسيط.*?تفضلاً", re.IGNORECASE),
)


def needs_arabic_fluency_repair(text: str) -> bool:
    """Return True for a small set of recurring literal-translation patterns."""
    value = clean_arabic_question(text)
    return any(pattern.search(value) for pattern in _ARABIC_AWKWARD_PATTERNS)


def build_arabic_repair_prompt(question: str) -> str:
    """Ask the Arabic model to repair a malformed generated question."""
    return f"""
النص التالي هو مخرج خام من نموذج لغوي. قم بتحويله حصراً إلى سؤال شفاهي طبيعي وسلس باللغة العربية الفصحى.

القواعد:
- أرجع نص السؤال فقط؛ لا تكتب أي مقدمة أو تفسير أو Markdown.
- تجنب عبارات مثل «باللغة العربية»، «السؤال:»، «سؤال:».
- يجب أن يكون السؤال موجهاً ومباشراً للطالب كأنك محاور شفاهي.
- حافظ على المصطلحات التقنية الإنجليزية مثل Python، def، return، API، SQL كما هي عند الحاجة.
- اضبط السؤال ليكون فصيحاً وطبيعياً أكاديمياً.

النص الخام:
{question}
""".strip()
