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
