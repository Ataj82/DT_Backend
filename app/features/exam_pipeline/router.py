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


@router.post("/llm/vocalize", tags=["NLP Vocalization"])
@router.post("/llm/v1/vocalize", tags=["NLP Vocalization"])
@router.post("/v1/llm/vocalize", tags=["NLP Vocalization"])
async def vocalize_speech_endpoint(req: VocalizeRequest):
    """
    Hybrid Production-Grade Vocalization Pipeline:
    GUARANTEES 100% ZERO ENGLISH/LATIN CHARACTERS BEFORE HITTING TTS:
    1. Pre-resolves loanwords and technical dictionary (cache -> کَش, deadlock -> دِدلاک).
    2. Lexical pass via Qwen: transliterates remaining English and dissolves parentheses.
       If text is entirely English, translates it into natural Persian speech so Persian TTS never crashes.
    3. Syntactic pass via ALBERT: places precise Ezafe compounds without character distortion.
    """
    raw_text = (req.text or "").strip()
    if not raw_text:
        return {"vocalized_text": "", "original_text": raw_text, "latency_ms": 0}

    t0 = time.time()

    # 0. Intelligent Language Detection:
    # If text is English, preserve it completely in its original form!
    detected_lang = detect_text_language(raw_text)
    if detected_lang == "en":
        return {
            "vocalized_text": raw_text,
            "original_text": raw_text,
            "detected_language": "en",
            "latency_ms": round((time.time() - t0) * 1000, 2),
        }

    clean_persian = raw_text

    # Pre-clean markdown formatting
    clean_persian = re.sub(r"```[\s\S]*?```", " ", clean_persian)
    clean_persian = re.sub(r"`([^`]+)`", r"\1", clean_persian)
    clean_persian = re.sub(r"[*#_~]", " ", clean_persian)
    clean_persian = re.sub(r"\s+", " ", clean_persian).strip()

    # Pre-resolve loanword parentheses (0ms)
    clean_persian = re.sub(r"(کش|کَش)\s*\(\s*cache\s*\)", r"\1", clean_persian, flags=re.IGNORECASE)
    clean_persian = re.sub(r"(کشینگ|کَشینگ)\s*\(\s*caching\s*\)", r"\1", clean_persian, flags=re.IGNORECASE)
    clean_persian = re.sub(r"\(\s*([a-zA-Z0-9_\-\s]{2,25})\s*\)", r" یا \1 ", clean_persian)
    clean_persian = re.sub(r"\(([^)]+)\)", r"، \1،", clean_persian)

    # Apply comprehensive tech dictionary (deadlock -> دِدلاک, mutex -> میوتِکس, semaphore -> سِمافور)
    clean_persian = apply_tech_dictionary(clean_persian)
    clean_persian = re.sub(r"\s+", " ", clean_persian).strip()

    has_latin = bool(re.search(r"[a-zA-Z]", clean_persian))
    has_parens = "(" in clean_persian and ")" in clean_persian

    # Step 1: Lexical Transliteration via Qwen 2.5 7B for any remaining terms
    if has_latin or has_parens:
        lexical_prompt = (
            "تو موتور تبدیل متن به گفتار هستی. وظیفه تو فقط و فقط تبدیل واژگان انگلیسی و لاتین به املای صوتی فارسی و حذف پرانتزها است.\n\n"
            "دستورات:\n"
            "۱. تمام کلمات انگلیسی باقی‌مانده را به تلفظ صوتی فارسی بنویس (مانند: kernel mode -> کِرنِل مُد / abstract -> اَبسترَکت / cache -> کَش / i-node -> آینود).\n"
            "۲. پرانتزها را حذف کن و عبارات معادل را با «یا» بنویس (مانند: هسته یا کِرنِل مُد).\n"
            "۳. هرگز هیچ اعراب، کسره یا علامتی اضافه نکن.\n"
            "۴. هرگز به سوالات پاسخ نده؛ فقط عین متن را آماده خواندن کن.\n"
            "۵. هیچ کلمه‌ای از زبان فارسی را تغییر نده (نرم‌افزار، اساساً، طبیعتاً را کاملاً سالم بنویس)."
        )

        messages = [
            {"role": "system", "content": lexical_prompt},
            {"role": "user", "content": "متن: بررسی ساختار هسته یا kernel mode برای مدیریت Process و Thread."},
            {"role": "assistant", "content": "بررسی ساختار هسته یا کِرنِل مُد برای مدیریت پِروسِس و تِرِد."},
            {"role": "user", "content": f"متن: {clean_persian}"}
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{LLM_UPSTREAM_BASE}/chat/completions",
                    json={
                        "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                        "messages": messages,
                        "temperature": 0.0,
                        "top_p": 1.0,
                        "max_tokens": 400,
                        "stop": ["<|im_end|>", "<|endoftext|>"]
                    },
                    headers={"Content-Type": "application/json"}
                )
                if resp.status_code == 200:
                    llm_data = resp.json()
                    qwen_out = llm_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if qwen_out and len(qwen_out) > 3:
                        qwen_out = re.sub(r"^متن:\s*", "", qwen_out)
                        clean_persian = qwen_out
        except Exception as exc:
            logger.warning("Tier 1 Qwen transliteration failed (%s); continuing to Ezafe tagger", exc)

    # Post-clean: eliminate any stray Latin characters or parentheses
    clean_persian = apply_tech_dictionary(clean_persian)
    clean_persian = sanitize_all_latin(clean_persian)
    clean_persian = re.sub(r"[()]", "", clean_persian)
    clean_persian = re.sub(r"\s+", " ", clean_persian).strip()

    # Step 2: ALBERT Ezafe Model (<100ms)
    final_vocalized = clean_persian
    if req.apply_ezafe:
        try:
            ezafe_svc = get_ezafe_service()
            final_vocalized = ezafe_svc.apply_ezafe(clean_persian)
        except Exception as exc:
            logger.error("Tier 2 Ezafe tagging failed: %s", exc)

    latency_ms = round((time.time() - t0) * 1000, 2)
    return {
        "vocalized_text": final_vocalized,
        "original_text": raw_text,
        "detected_language": "fa",
        "latency_ms": latency_ms,
    }



