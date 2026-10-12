"""
features/exam_pipeline/tech_dictionary.py

Comprehensive Computer Science & Engineering phonetic transliteration dictionary.
Converts Latin terms, abbreviations, and acronyms to standard Iranian academic Persian pronunciations.
"""

import re
from typing import Dict, List, Tuple

# Technical terms ordered by longest/most-specific match first
TECH_TERMS_RAW: List[Tuple[str, str]] = [
    # Multi-word phrases
    (r"\b3-way handshake\b", "تری‌وی هَندشِیک"),
    (r"\bthree-way handshake\b", "تری‌وی هَندشِیک"),
    (r"\buser thread\b", "یوزِر تِرِد"),
    (r"\buser threads\b", "یوزِر تِرِدهٰا"),
    (r"\bkernel thread\b", "کِرنِل تِرِد"),
    (r"\bkernel threads\b", "کِرنِل تِرِدهٰا"),
    (r"\bkernel mode\b", "کِرنِل مُد"),
    (r"\buser mode\b", "یوزِر مُد"),
    (r"\buser space\b", "یوزِر اِسپِیس"),
    (r"\bkernel space\b", "کِرنِل اِسپِیس"),
    (r"\bcontext switch\b", "کانتِکست سوییچ"),
    (r"\bcontext switching\b", "کانتِکست سوییچینگ"),
    (r"\bround robin\b", "راوند رابین"),
    (r"\brace condition\b", "رِیس کاندیشِن"),
    (r"\bcritical section\b", "کریتیکال سِکشِن"),
    (r"\bpage fault\b", "پِیج فالت"),
    (r"\bpage faults\b", "پِیج فالت‌هٰا"),
    (r"\bpage table\b", "پِیج تِیبِل"),
    (r"\bvirtual memory\b", "ویرچوال مِموری"),
    (r"\bsystem call\b", "سیستِم کال"),
    (r"\bsystem calls\b", "سیستِم کال‌هٰا"),
    (r"\bprimary key\b", "پرایمِری کی"),
    (r"\bforeign key\b", "فورِن کی"),
    (r"\binner join\b", "اینِر جویْن"),
    (r"\bouter join\b", "اوتر جویْن"),
    (r"\blinked list\b", "لینکِد لیست"),
    (r"\bhash table\b", "هَش تِیبِل"),
    (r"\bhash map\b", "هَش‌مَپ"),
    (r"\bbinary tree\b", "باینِری تِری"),
    (r"\bred-black tree\b", "رِد بلَک تِری"),
    (r"\bmac address\b", "مَک آدْرِس"),
    (r"\bfile system\b", "فایل‌سیستِم"),
    (r"\bfilesystem\b", "فایل‌سیستِم"),
    (r"\boperating system\b", "سیستم‌عامل"),
    (r"\boperating systems\b", "سیستم‌هایِ عامل"),

    # Hardware & Architectures
    (r"\bi-node\b", "آی‌نود"),
    (r"\binode\b", "آی‌نود"),
    (r"\bi-nodes\b", "آی‌نودها"),
    (r"\binodes\b", "آی‌نودها"),
    (r"\bx86\b", "ایکس هشتاد و شش"),
    (r"\bx64\b", "ایکس شصت و چهار"),
    (r"\barm\b", "آرم"),
    (r"\bcpu\b", "سی‌پی‌یو"),
    (r"\bcpus\b", "سی‌پی‌یوها"),
    (r"\bgpu\b", "جی‌پی‌یو"),
    (r"\bgpus\b", "جی‌پی‌یوها"),
    (r"\bram\b", "رَم"),
    (r"\brom\b", "رام"),
    (r"\bssd\b", "اس‌اس‌دی"),
    (r"\bhdd\b", "اچ‌دی‌دی"),
    (r"\bi/o\b", "آی‌او"),
    (r"\bio\b", "آی‌او"),
    (r"\bmmu\b", "ام‌ام‌یو"),
    (r"\balu\b", "ای‌ال‌یو"),
    (r"\bbus\b", "باس"),
    (r"\bcore\b", "کور"),
    (r"\bcores\b", "کورها"),
    (r"\bregister\b", "رِجیستِر"),
    (r"\bregisters\b", "رِجیستِرهٰا"),

    # OS & Concurrency
    (r"\bthread\b", "تِرِد"),
    (r"\bthreads\b", "تِرِدهٰا"),
    (r"\bmultithreading\b", "مالتی‌ترِدینگ"),
    (r"\bmulti-threading\b", "مالتی‌ترِدینگ"),
    (r"\bprocess\b", "پِروسِس"),
    (r"\bprocesses\b", "پِروسِس‌هٰا"),
    (r"\bmultiprocessing\b", "مالتی‌پِروسِسینگ"),
    (r"\bmulti-processing\b", "مالتی‌پِروسِسینگ"),
    (r"\bdeadlock\b", "دِدلاک"),
    (r"\bdeadlocks\b", "دِدلاک‌هٰا"),
    (r"\bmutex\b", "میوتِکس"),
    (r"\bmutexes\b", "میوتِکس‌هٰا"),
    (r"\bsemaphore\b", "سِمافور"),
    (r"\bsemaphores\b", "سِمافورها"),
    (r"\bkernel\b", "کِرنِل"),
    (r"\buser\b", "یوزِر"),
    (r"\bcache\b", "کَش"),
    (r"\bcaching\b", "کَشینگ"),
    (r"\bbuffer\b", "بافِر"),
    (r"\bbuffers\b", "بافِرهٰا"),
    (r"\bpaging\b", "پِیجینگ"),
    (r"\bsegmentation\b", "سِگمِنتِیشِن"),
    (r"\bmemory\b", "مِموری"),
    (r"\bstarvation\b", "استاروِیشِن"),
    (r"\blivelock\b", "لایولاک"),
    (r"\bpcb\b", "پی‌سی‌بی"),
    (r"\btcb\b", "تی‌سی‌بی"),
    (r"\bipc\b", "آی‌پی‌سی"),
    (r"\bpipe\b", "پایپ"),
    (r"\bpipes\b", "پایپ‌هٰا"),
    (r"\bsignal\b", "سیگنال"),
    (r"\bsignals\b", "سیگنال‌هٰا"),
    (r"\bsyscall\b", "سیس‌کال"),
    (r"\bsyscalls\b", "سیس‌کال‌هٰا"),
    (r"\binterrupt\b", "اینتِراپت"),
    (r"\binterrupts\b", "اینتِراپت‌هٰا"),
    (r"\bscheduling\b", "اِسکِجولینگ"),
    (r"\bscheduler\b", "اِسکِجولِر"),
    (r"\bmode\b", "مُد"),
    (r"\babstract\b", "اَبسترَکت"),
    (r"\babstraction\b", "اَبسترَکشِن"),
    (r"\bcontext\b", "کانتِکست"),

    # Data Structures & Algorithms
    (r"\bstack\b", "استَک"),
    (r"\bqueue\b", "کیو"),
    (r"\bdeque\b", "دِک"),
    (r"\bpush\b", "پوش"),
    (r"\bpop\b", "پاپ"),
    (r"\bheap\b", "هیپ"),
    (r"\btree\b", "تِری"),
    (r"\bbst\b", "بی‌اس‌تی"),
    (r"\bavl\b", "ای‌وی‌ال"),
    (r"\bgraph\b", "گِراف"),
    (r"\bnode\b", "نود"),
    (r"\bnodes\b", "نودهٰا"),
    (r"\bvertex\b", "وِرتِکس"),
    (r"\bedge\b", "اِج"),
    (r"\bhashmap\b", "هَش‌مَپ"),
    (r"\bbig-o\b", "بیگ‌او"),
    (r"\bbig o\b", "بیگ‌او"),
    (r"\bo\(1\)\b", "او یِک"),
    (r"\bo\(n\)\b", "او اِن"),
    (r"\bo\(log\s*n\)\b", "او لاگ اِن"),
    (r"\bo\(n\^2\)\b", "او اِن دو"),
    (r"\bdfs\b", "دی‌اف‌اس"),
    (r"\bbfs\b", "بی‌اف‌اس"),

    # Networks
    (r"\btcp\b", "تی‌سی‌پی"),
    (r"\budp\b", "یو‌دی‌پی"),
    (r"\bip\b", "آی‌پی"),
    (r"\bipv4\b", "آی‌پی ورژن چهار"),
    (r"\bipv6\b", "آی‌پی ورژن شش"),
    (r"\bdns\b", "دی‌ان‌اس"),
    (r"\bdhcp\b", "دی‌اچ‌سی‌پی"),
    (r"\bhttp\b", "اچ‌تی‌تی‌پی"),
    (r"\bhttps\b", "اچ‌تی‌تی‌پی‌اس"),
    (r"\bftp\b", "اف‌تی‌پی"),
    (r"\bssh\b", "اس‌اس‌اچ"),
    (r"\bssl\b", "اس‌اس‌ال"),
    (r"\btls\b", "تی‌ال‌اس"),
    (r"\bosi\b", "او‌اِس‌آی"),
    (r"\blan\b", "لَن"),
    (r"\bwan\b", "وَن"),
    (r"\bvlan\b", "وی‌لَن"),
    (r"\bnat\b", "نَت"),
    (r"\bvpn\b", "وی‌پی‌ان"),
    (r"\bpacket\b", "پَکِت"),
    (r"\bpackets\b", "پَکِت‌هٰا"),
    (r"\bframe\b", "فِرِیم"),
    (r"\bframes\b", "فِرِیم‌هٰا"),
    (r"\bsocket\b", "ساکِت"),
    (r"\bsockets\b", "ساکِت‌هٰا"),
    (r"\bport\b", "پورت"),
    (r"\bports\b", "پورت‌هٰا"),
    (r"\brouter\b", "روتر"),
    (r"\bswitch\b", "سوییچ"),
    (r"\bhub\b", "هاب"),

    # Database
    (r"\bsql\b", "اس‌کیواِل"),
    (r"\bnosql\b", "نو‌اس‌کیواِل"),
    (r"\bindex\b", "اینْدِکس"),
    (r"\bindexes\b", "اینْدِکس‌هٰا"),
    (r"\bjoin\b", "جویْن"),
    (r"\bquery\b", "کوئِری"),
    (r"\bqueries\b", "کوئِری‌هٰا"),
    (r"\btable\b", "تِیبِل"),
    (r"\bschema\b", "اسکیما"),
    (r"\bacid\b", "اَسید"),
    (r"\btransaction\b", "تِرَنزَکشِن"),
    (r"\btransactions\b", "تِرَنزَکشِن‌هٰا"),

    # AI & Software Eng
    (r"\bai\b", "هوش مصنوعی"),
    (r"\bapi\b", "ای‌پی‌آی"),
    (r"\brest\b", "رِست"),
    (r"\bjson\b", "جِیسان"),
    (r"\bgit\b", "گیت"),
    (r"\bserver\b", "سِروِر"),
    (r"\bservers\b", "سِروِرهٰا"),
    (r"\bclient\b", "کلاینت"),
    (r"\bclients\b", "کلاینت‌هٰا"),
    (r"\bfrontend\b", "فرانت‌اند"),
    (r"\bbackend\b", "بَک‌اند"),
    (r"\bdocker\b", "داکِر"),
    (r"\bcontainer\b", "کانتِینِر"),
    (r"\bcontainers\b", "کانتِینِرهٰا"),
    (r"\bbug\b", "باگ"),
    (r"\bdebug\b", "دی‌باگ"),
    (r"\bblock\b", "بلوک"),
    (r"\bblocks\b", "بلوک‌هٰا"),
    (r"\bdirectory\b", "دایرِکتوری"),
    (r"\bdirectories\b", "دایرِکتوری‌هٰا"),
]

# Compile patterns for fast sub-millisecond execution
COMPILED_TERMS = [(re.compile(pat, re.IGNORECASE), rep) for pat, rep in TECH_TERMS_RAW]

LATIN_LETTER_PHONETIC = {
    "a": "اِی", "b": "بی", "c": "سی", "d": "دی", "e": "ای", "f": "اف", "g": "جی",
    "h": "اچ", "i": "آی", "j": "جِی", "k": "کِی", "l": "ال", "m": "ام", "n": "ان",
    "o": "او", "p": "پی", "q": "کیو", "r": "آر", "s": "اس", "t": "تی", "u": "یو",
    "v": "وی", "w": "دابلیو", "x": "ایکس", "y": "وای", "z": "زد"
}


def apply_tech_dictionary(text: str) -> str:
    """
    Substitutes all standard technical English terms with Persian academic phonetics.
    """
    if not text:
        return ""
    res = text
    for pattern, rep in COMPILED_TERMS:
        res = pattern.sub(rep, res)
    return res


def sanitize_all_latin(text: str) -> str:
    """
    Guarantees 100% ZERO Latin characters remain in the text.
    Any leftover Latin acronyms or letters are converted to Persian phonetics.
    """
    if not text:
        return ""
    res = text
    # Convert remaining Latin words/letters to phonetic Persian
    def _repl(match):
        word = match.group(0).lower()
        return "‌".join(LATIN_LETTER_PHONETIC.get(ch, ch) for ch in word)

    res = re.sub(r"[a-zA-Z]+", _repl, res)
    return res


PERSIAN_STRUCTURAL_WORDS = {
    "در", "به", "با", "از", "برای", "که", "تا", "و", "یا", "این", "آن", "است", "شد", "بود",
    "باشد", "می‌شود", "میشود", "توضیح", "دهید", "کنید", "چیست", "چگونه", "چرا", "کدام",
    "آیا", "بررسی", "تعریف", "مقایسه", "نقش", "تفاوت", "بین", "نحوه", "عملکرد", "سیستم",
    "حافظه", "مدیریت", "انجام", "مگر", "حتی", "نیز", "همیشه", "نیست", "کاربرد", "برنامه",
    "سخت‌افزار", "نرم‌افزار", "پردازش", "پاسخ", "مفاهیم", "ساختار", "روان", "روش", "چند",
    "یک", "دو", "سه", "چهار", "پنج", "مورد", "مزایا", "معایب", "ویژگی", "ویژگی‌های",
    "را", "هم", "دیگر", "یکدیگر", "بگوییم", "اجرا", "دارند", "ارائه", "مجموعه", "حل"
}

ENGLISH_STRUCTURAL_WORDS = {
    "the", "is", "are", "was", "were", "of", "in", "to", "and", "a", "an", "that", "this",
    "for", "as", "with", "by", "on", "at", "from", "which", "what", "how", "why", "who",
    "when", "where", "explain", "describe", "compare", "based", "provided", "act", "acts",
    "provide", "consisting", "running", "parallel", "hide", "effects", "between", "does",
    "do", "did", "can", "could", "would", "should", "will", "discuss", "define", "outline",
    "list", "following", "true", "false", "difference", "differences"
}


def detect_text_language(text: str) -> str:
    """
    Intelligently determines if text is primarily English or Persian with English loanwords:
    - If pure English: returns 'en' (must be preserved untouched).
    - If Persian sentence with English technical terms: returns 'fa' (must be vocalized to Persian).
    """
    clean = (text or "").strip()
    if not clean:
        return "fa"

    # Strip metadata/question numbering prefixes (e.g. "سوال ۱:", "Question 2:")
    clean_body = re.sub(
        r"^(?:سوال|پرسش|پاسخ|تمرین|تست|درس|question|q)\s*\d*[\s:\-—]*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()

    persian_chars = len(re.findall(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]", clean_body))
    if persian_chars == 0:
        return "en"

    latin_chars = len(re.findall(r"[a-zA-Z]", clean_body))
    if latin_chars == 0:
        return "fa"

    persian_words = set(re.findall(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]+", clean_body.lower()))
    latin_words = set(re.findall(r"[a-zA-Z]+", clean_body.lower()))

    fa_structural = len(persian_words & PERSIAN_STRUCTURAL_WORDS)
    en_structural = len(latin_words & ENGLISH_STRUCTURAL_WORDS)

    # If predominantly English sentence structure (English verbs/prepositions without Persian structural tokens)
    if en_structural >= 2 and fa_structural == 0:
        return "en"

    # If Persian structure or multiple Persian words present, it is a Persian sentence with loanwords
    if fa_structural >= 1 or len(persian_words) >= 2:
        return "fa"

    return "fa" if len(persian_words) >= len(latin_words) else "en"

