"""
features/exam_pipeline/router.py

Master APIRouter unifying all sub-routers of the Adaptive Exam Framework.
"""

from __future__ import annotations

from fastapi import APIRouter

from .api.routers import (
    abet_router,
    assessment_router,
    exam_requests,
    goal_router,
    interview_router,
    knowledge_router,
    multiuser,
    reports,
)
from .production.readiness import check_readiness

router = APIRouter()

# 1. Exam Requests & Frontend Integration (CreateExamAccordion, etc.)
router.include_router(exam_requests.router)

# 2. Goals Management & Authoring
router.include_router(goal_router.router)

# 3. Interviews & Adaptive Assessments
router.include_router(interview_router.router)
router.include_router(interview_router.abet_interview_router)

# 4. Multi-User Assignments & Cohort Progress
router.include_router(multiuser.router)

# 5. Knowledge Ingestion & Concepts
router.include_router(knowledge_router.router)

# 6. ABET Criteria & Outcomes
router.include_router(abet_router.router)

# 7. Psychometric Reports & Telemetry
router.include_router(reports.router)

# 8. Assessment Engine Endpoints
router.include_router(assessment_router.router)


@router.get("/health", tags=["Exam Pipeline System"])
async def exam_pipeline_health():
    """Health status of the adaptive exam pipeline."""
    return {"status": "ok", "system": "Adaptive AI Exam Pipeline"}


@router.get("/ready", tags=["Exam Pipeline System"])
async def exam_pipeline_readiness():
    """Readiness probes for LLM provider, storage, and configuration."""
    report = check_readiness()
    return {
        "status": "ready" if report.ready else "not_ready",
        "ready": report.ready,
        "checks": report.checks,
        "warnings": report.warnings,
    }


# ==========================================================
# 9. LLM Gateway & Transparent Proxy
# Base: http://94.184.177.171:8000/v1
# Proxies browser requests to bypass HTTPS Mixed Content blocks
# ==========================================================
import httpx
from fastapi import Request, Response, HTTPException

LLM_UPSTREAM_BASE = "http://94.184.177.171:8000/v1"


@router.post("/llm/chat/completions", tags=["LLM Gateway"])
@router.post("/llm/v1/chat/completions", tags=["LLM Gateway"])
@router.post("/v1/chat/completions", tags=["LLM Gateway"])
async def proxy_llm_chat_completions(request: Request):
    """
    Transparent proxy to Qwen LLM at http://94.184.177.171:8000/v1/chat/completions.
    Bypasses browser mixed-content violations on HTTPS origins.
    """
    target_url = f"{LLM_UPSTREAM_BASE}/chat/completions"
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                target_url,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json",
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM proxy error: {str(exc)}")


@router.get("/llm/models", tags=["LLM Gateway"])
@router.get("/llm/v1/models", tags=["LLM Gateway"])
@router.get("/v1/models", tags=["LLM Gateway"])
async def proxy_llm_models():
    """
    Proxy to Qwen LLM models list at http://94.184.177.171:8000/v1/models.
    """
    target_url = f"{LLM_UPSTREAM_BASE}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(target_url)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json",
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM models proxy error: {str(exc)}")


# ==========================================================
# 10. Hybrid Speech Vocalization & Ezafe Engine
# Tier 1: Qwen 2.5 7B Lexical Transliteration (Zero Diacritic Penalty)
# Tier 2: ALBERT HomoRich Persian Ezafe Tagger (<100ms, 98.7% F1)
# ==========================================================
import re
import time
from pydantic import BaseModel
from .ezafe_service import get_ezafe_service
from .tech_dictionary import apply_tech_dictionary, sanitize_all_latin, detect_text_language


class VocalizeRequest(BaseModel):
    text: str
    course_context: str = "سیستم‌های عامل"
    apply_ezafe: bool = True


@router.post("/nlp/ezafe", tags=["NLP Vocalization"])
@router.post("/llm/ezafe", tags=["NLP Vocalization"])
async def tag_ezafe_endpoint(req: VocalizeRequest):
    """
    Direct high-speed Persian Ezafe diacritization using ALBERT model (<100ms).
    """
    if not req.text or not req.text.strip():
        return {"vocalized_text": "", "original_text": req.text}

    t0 = time.time()
    ezafe_svc = get_ezafe_service()
    vocalized = ezafe_svc.apply_ezafe(req.text)
    latency_ms = round((time.time() - t0) * 1000, 2)
    return {
        "vocalized_text": vocalized,
        "original_text": req.text,
        "latency_ms": latency_ms,
    }


def enhance_punctuation_for_tts(text: str) -> str:
    """
    Enhances text with punctuation (commas and periods) to create natural pauses and phrasing for TTS,
    replacing phonetic diacritics / vowels. Preserves English words completely.
    """
    if not text:
        return ""
    # 1. Remove all diacritics/اعراب
    res = re.sub(r'[\u064B-\u065F\u0670ـِ]', '', text)

    # 2. Normalize markdown & special chars
    res = re.sub(r'[{}\[\]_#*\\/|~^]', ' ', res)
    res = re.sub(r'[:;؛]', '،', res)
    res = re.sub(r'[\u061F\?]+', '؟', res)
    res = re.sub(r'[!]+', '.', res)

    # 3. Commas before major conjunctions if not already punctuated
    conjunctions = [
        'چرا که', 'چراکه', 'به‌طوری‌که', 'به طوری که', 'به همین دلیل',
        'در نتیجه', 'بنابراین', 'از این رو', 'همچنین', 'اما', 'ولی', 'زیرا', 'بلکه'
    ]
    for conj in conjunctions:
        res = re.sub(rf'(?<![،,.:؛?!؟\s])\s+({conj})\b', r'، \1', res)

    # 'که' with negative lookbehind to avoid 'این‌که', 'آن‌که'
    res = re.sub(r'(?<![،,.:؛?!؟\s\u200c])\s+(که)\b', r'، که', res)

    # 4. Commas after introductory phrases
    intro_phrases = [
        'به عنوان مثال', 'برای نمونه', 'مثلاً', 'مثلا', 'در واقع',
        'به طور کلی', 'به‌طور کلی', 'از طرفی', 'از سوی دیگر', 'در این حالت', 'در این صورت', 'در نهایت'
    ]
    for intro in intro_phrases:
        res = re.sub(rf'(^|[.،؟!\n]\s*)({intro})\s+(?![،,])', r'\1\2، ', res)

    # 5. Question/Numbered list prefixes
    res = re.sub(r'^(سوال|پرسش|مورد|بخش)\s*([۰-۹\d]+)\s*[:\-—]', r'\1 \2. ', res, flags=re.MULTILINE)
    res = re.sub(r'^([۰-۹\d]+)\s*[\-—]\s*', r'\1. ', res, flags=re.MULTILINE)

    # 6. Deduplicate & cleanup punctuation and spacing
    res = re.sub(r'\s*،\s*', '، ', res)
    res = re.sub(r'،(\s*،)+', '،', res)
    res = re.sub(r'\s*\.\s*', '. ', res)
    res = re.sub(r'\.(\s*\.)+', '.', res)
    res = re.sub(r'،\s*\.', '.', res)
    res = re.sub(r'،\s*؟', '؟', res)
    res = re.sub(r'\.\s*؟', '؟', res)
    res = re.sub(r'\s+', ' ', res).strip()

    # 7. Ensure ending punctuation
    if res and not re.search(r'[.؟!؟]$', res):
        res += '.'

    return res


@router.post("/llm/vocalize", tags=["NLP Vocalization"])
@router.post("/llm/v1/vocalize", tags=["NLP Vocalization"])
@router.post("/v1/llm/vocalize", tags=["NLP Vocalization"])
async def vocalize_speech_endpoint(req: VocalizeRequest):
    """
    TTS Text Normalization Pipeline:
    1. Preserves English words completely as English (read by dedicated English model).
    2. Resolves parentheses with 'یا' and pause commas (e.g. 'هسته (kernel)' -> 'هسته، یا kernel،').
    3. Uses punctuation (commas and periods) for natural breathing pauses instead of phonetic diacritics.
    """
    raw_text = (req.text or "").strip()
    if not raw_text:
        return {"vocalized_text": "", "original_text": raw_text, "latency_ms": 0}

    t0 = time.time()

    # 0. Intelligent Language Detection:
    # If text is entirely English, preserve it completely
    detected_lang = detect_text_language(raw_text)
    if detected_lang == "en":
        return {
            "vocalized_text": raw_text,
            "original_text": raw_text,
            "detected_language": "en",
            "latency_ms": round((time.time() - t0) * 1000, 2),
        }

    clean_persian = raw_text

    # 1. Pre-clean markdown formatting
    clean_persian = re.sub(r"```[\s\S]*?```", " ", clean_persian)
    clean_persian = re.sub(r"`([^`]+)`", r"\1", clean_persian)
    clean_persian = re.sub(r"[*#_~]", " ", clean_persian)
    clean_persian = re.sub(r"\s+", " ", clean_persian).strip()

    # 2. Intelligent Parentheses Resolution:
    # A. Loanword deduplication: e.g. کش (cache) -> کش
    clean_persian = re.sub(r"(کش|کَش)\s*\(\s*cache\s*\)", r"\1", clean_persian, flags=re.IGNORECASE)
    clean_persian = re.sub(r"(کشینگ|کَشینگ)\s*\(\s*caching\s*\)", r"\1", clean_persian, flags=re.IGNORECASE)

    # B. Persian word + (EnglishTerm) -> PersianWord، یا EnglishTerm،
    clean_persian = re.sub(r"([\u0600-\u06FF]+)\s*\(\s*([a-zA-Z0-9_\-\s]{2,30})\s*\)", r"\1، یا \2،", clean_persian)

    # C. Standalone (EnglishTerm) -> ، یا EnglishTerm،
    clean_persian = re.sub(r"\(\s*([a-zA-Z0-9_\-\s]{2,30})\s*\)", r"، یا \1،", clean_persian)

    # D. General explanatory parentheses -> ، توضیح،
    clean_persian = re.sub(r"\(([^)]+)\)", r"، \1،", clean_persian)
    clean_persian = re.sub(r"[()]", "", clean_persian)

    # 3. Add punctuation (dots and commas) for natural phrasing instead of diacritics/اعراب
    final_vocalized = enhance_punctuation_for_tts(clean_persian)

    latency_ms = round((time.time() - t0) * 1000, 2)
    return {
        "vocalized_text": final_vocalized,
        "original_text": raw_text,
        "detected_language": "fa",
        "latency_ms": latency_ms,
    }



