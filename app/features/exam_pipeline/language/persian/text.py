"""Small Persian-only text normalization helpers.

These helpers deliberately operate only on the Persian language path.  They do
not translate technical identifiers; standard code/API terms are preserved and
visually separated from Persian prose.
"""
from __future__ import annotations

import re

from ..resolver import detect_text_language

# Common model prefixes that turn a question into meta-text instead of a clean
# interviewer utterance.  Matching is intentionally conservative.
_QUESTION_PREFIX_RE = re.compile(
    r"^(?:\s*(?:\*\*)?(?:سؤال|سوال|question)(?:\*\*)?\s*[:：-]\s*)+",
    flags=re.IGNORECASE,
)
_META_PREFIX_RE = re.compile(
    r"^\s*(?:به\s+زبان\s+فارسی|در\s+زبان\s+فارسی|پاسخ\s+فارسی|خروجی\s+فارسی)"
    r"(?:[^:：\n]*[:：]\s*)",
    flags=re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"^```(?:text|markdown|plain|fa|persian)?\s*|\s*```$", re.IGNORECASE)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_LATIN_TOKEN_RE = re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9_.+#/-]*(?![A-Za-z])")
_PERSIAN_LETTER_RE = re.compile(r"[\u0600-\u06ff]")


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_persian_concept(label: str) -> str:
    """Return a readable Persian concept phrase while preserving identifiers."""
    text = _clean_space(str(label or "")).strip(" .،؛:")
    if not text:
        return "مفهوم موردنظر"

    # Keep technical identifiers (Python, def, return, API, SQL, ...) exactly as
    # supplied, but set them apart from Persian prose using Persian guillemets.
    def quote_token(match: re.Match[str]) -> str:
        token = match.group(0)
        # Do not quote a token that is already inside a guillemet pair.
        return f"«{token}»"

    text = _LATIN_TOKEN_RE.sub(quote_token, text)
    return text


_COMMON_PERSIAN_CONCEPTS = {
    "python": "پایتون",
    "python functions": "توابع پایتون",
    "functions": "توابع",
    "function": "تابع",
    "python variables": "متغیرهای پایتون",
    "variables": "متغیرها",
    "variable": "متغیر",
    "loop": "حلقه",
    "loops": "حلقه‌ها",
    "conditional": "دستورهای شرطی",
    "conditionals": "دستورهای شرطی",
    "class": "کلاس",
    "classes": "کلاس‌ها",
    "object": "شیء",
    "objects": "اشیا",
    "list": "فهرست",
    "lists": "فهرست‌ها",
    "dictionary": "دیکشنری",
    "dictionaries": "دیکشنری‌ها",
    "exception": "استثنا",
    "exceptions": "استثناها",
    "recursion": "بازگشت",
    "scope": "محدوده دسترسی",
}

_TECHNICAL_KEYWORDS = {
    "def": "دستور «def» در پایتون",
    "return": "دستور «return» در پایتون",
    "class": "کلاس در پایتون",
    "import": "دستور «import» در پایتون",
}


def _persian_concept_phrase(label: str) -> str:
    text = _clean_space(str(label or "")).strip(" .،؛:")
    if not text:
        return "مفهوم موردنظر"

    key = text.casefold()
    if key in _TECHNICAL_KEYWORDS:
        return _TECHNICAL_KEYWORDS[key]
    if key in _COMMON_PERSIAN_CONCEPTS:
        return _COMMON_PERSIAN_CONCEPTS[key]

    # Handle common Python concepts written as English phrases without
    # translating arbitrary technical identifiers.
    normalized = key.replace("_", " ")
    if normalized in _COMMON_PERSIAN_CONCEPTS:
        return _COMMON_PERSIAN_CONCEPTS[normalized]

    return format_persian_concept(text)


def build_persian_goal_title(label: str) -> str:
    concept = _persian_concept_phrase(label)
    if concept.startswith("دستور «") and " در پایتون" in concept:
        return f"درک کاربرد {concept}"
    if concept in {"توابع پایتون", "متغیرهای پایتون", "دستورهای شرطی"}:
        return f"درک {concept}"
    if concept == "پایتون":
        return "درک مفاهیم پایه پایتون"
    return f"درک مفهوم {concept}"


def build_persian_goal_description(label: str, description: str | None) -> str:
    source = _clean_space(str(description or "")).strip(" .،؛:")
    concept = _persian_concept_phrase(label)

    # Prefer a fluent, learner-facing sentence over copying a source fragment
    # verbatim. Persian source descriptions are retained when they already
    # form a meaningful sentence; otherwise the goal is rebuilt from the
    # localized concept phrase.
    if source and detect_text_language(source) == "fa":
        cleaned_source = re.sub(r"^نشان\s+دادن\s+درک(?:\s+مفهوم)?\s*", "درک ", source)
        cleaned_source = re.sub(r"^توضیح\s+مفهوم\s*", "توضیح ", cleaned_source)
        if concept.startswith("دستور «") and " در پایتون" in concept:
            return f"یادگیرنده باید بتواند {concept} را توضیح دهد و یک کاربرد ساده برای آن بیان کند."
        if cleaned_source != source:
            return f"یادگیرنده باید بتواند {cleaned_source} را توضیح دهد و آن را در یک مثال ساده به کار ببرد."
        return f"یادگیرنده باید بتواند {source} را توضیح دهد و کاربرد آن را بیان کند."

    if concept.startswith("دستور «") and " در پایتون" in concept:
        return f"یادگیرنده باید بتواند {concept} را توضیح دهد و یک کاربرد ساده برای آن بیان کند."
    if concept in {"توابع پایتون", "متغیرهای پایتون", "دستورهای شرطی"}:
        return f"یادگیرنده باید بتواند {concept} را توضیح دهد و کاربرد آن را بیان کند."
    if concept == "پایتون":
        return "یادگیرنده باید بتواند مفاهیم پایه پایتون را توضیح دهد و کاربرد آن‌ها را بیان کند."
    return f"یادگیرنده باید بتواند مفهوم {concept} را توضیح دهد و کاربرد آن را بیان کند."



def build_persian_fallback_questions(topic: str) -> list[str]:
    """Return natural Persian fallback questions for generation failures."""
    raw = _clean_space(str(topic or "")).strip(" .،؛:") or "موضوع موردنظر"
    key = raw.casefold()
    concept = _TECHNICAL_KEYWORDS.get(key) or _COMMON_PERSIAN_CONCEPTS.get(key)
    if concept is None:
        concept = _COMMON_PERSIAN_CONCEPTS.get(key.replace("_", " "))
    if concept is None:
        concept = format_persian_concept(raw)
    return [
        f"{concept} چیست و چه کاربردی دارد؟ یک مثال ساده هم بزنید.",
        f"اگر بخواهید {concept} را در یک مسئله عملی به کار ببرید، از کجا شروع می‌کنید و نتیجه را چگونه بررسی می‌کنید؟",
        f"یک مثال مشخص از {concept} بزنید و توضیح دهید از کجا می‌فهمید راه‌حل شما درست است.",
        f"{concept} را با زبان خودتان توضیح دهید و بگویید در چه موقعیتی استفاده از آن مناسب است.",
    ]

def clean_persian_question(text: str) -> str:
    """Remove common LLM meta-wrappers while preserving the generated question."""
    value = str(text or "").strip()
    value = _CODE_FENCE_RE.sub("", value).strip()
    value = _MARKDOWN_BOLD_RE.sub(r"\1", value).strip()
    value = _INLINE_CODE_RE.sub(r"\1", value).strip()

    # Remove a common meta introduction first; after that the explicit
    # سؤال:/سوال: marker can be recognized even when the model placed a
    # technical token before it.
    value = _META_PREFIX_RE.sub("", value, count=1).strip()

    # Prefer the content after an explicit سؤال:/سوال: marker.  The marker
    # may be preceded by a technical token that the model echoed from context.
    match = re.search(r"(?:^|\n)\s*(?:سؤال|سوال|question)\s*[:：-]\s*", value, flags=re.IGNORECASE)
    if match:
        value = value[match.end():].strip()
    else:
        near_start = re.search(r"(?:سؤال|سوال|question)\s*[:：-]\s*", value[:120], flags=re.IGNORECASE)
        if near_start:
            value = value[near_start.end():].strip()
        else:
            value = _QUESTION_PREFIX_RE.sub("", value).strip()

    # If the model wrote a short meta sentence followed by the actual question,
    # discard the leading meta sentence when a Persian question remains.
    if "؟" in value:
        first_q = value.find("؟")
        candidate = value[: first_q + 1].strip()
        if _PERSIAN_LETTER_RE.search(candidate):
            value = candidate
    elif "?" in value:
        first_q = value.find("?")
        candidate = value[: first_q + 1].strip()
        if _PERSIAN_LETTER_RE.search(candidate):
            value = candidate

    return _clean_space(value)


def is_likely_persian_question(text: str) -> bool:
    """Conservative quality gate used only for Persian question generation."""
    value = clean_persian_question(text)
    if len(value) < 8 or not _PERSIAN_LETTER_RE.search(value):
        return False
    # A generated oral question should normally contain a Persian or ASCII
    # question mark.  Some models omit it, so accept a short interrogative form
    # beginning with common Persian question words as a fallback.
    if "؟" in value or "?" in value:
        return True
    return bool(re.match(r"^(?:چرا|چگونه|چطور|چه|کدام|آیا|در\s+چه|به\s+نظر|اگر|یک|دستور)", value))


_PERSIAN_AWKWARD_PATTERNS = (
    re.compile(r"\bمفهوم\s+(?:def|return|class|import)\b.*?چه کاربردی دارد", re.IGNORECASE),
    re.compile(r"می‌توانید\s+یک\s+مثال\s+ساده.*?بیان\s+کنید", re.IGNORECASE),
    re.compile(r"مثال\s+ساده\s+از\s+استفاده\s+از\s+آن", re.IGNORECASE),
)


def needs_persian_fluency_repair(text: str) -> bool:
    """Return True for a small set of recurring literal-translation patterns."""
    value = clean_persian_question(text)
    return any(pattern.search(value) for pattern in _PERSIAN_AWKWARD_PATTERNS)


def build_persian_repair_prompt(question: str) -> str:
    """Ask the Persian model to repair a malformed generated question."""
    return f"""
متن زیر خروجی خام یک مدل زبانی است. آن را فقط به یک سؤال شفاهی، طبیعی و روان به زبان فارسی تبدیل کنید.

قواعد:
- فقط خود سؤال را برگردانید؛ هیچ مقدمه، برچسب، توضیح یا Markdown ننویسید.
- از عبارت‌هایی مانند «به زبان فارسی»، «سؤال:»، «سوال:» یا «خروجی» استفاده نکنید.
- سؤال باید مستقیماً برای یک دانشجو قابل طرح باشد.
- اصطلاحات فنی استاندارد مانند Python، def، return، API و SQL را در صورت نیاز به همان شکل اصلی نگه دارید.
- سؤال را از نظر دستور زبان و لحن گفتاری فارسی طبیعی کنید؛ از ساختارهای تحت‌اللفظی مانند «مفهوم def چه کاربردی دارد» یا «یک مثال ساده از استفاده از آن بیان کنید» استفاده نکنید.
- برای def از ساختار طبیعی «دستور def در پایتون» استفاده کنید.

متن خام:
{question}
""".strip()
