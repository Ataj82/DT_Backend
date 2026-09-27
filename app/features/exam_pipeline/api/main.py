"""
app/api/main.py

FastAPI application entry point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..api.dependencies import get_framework

from ..api.routers.knowledge_router import router as knowledge_router
from ..api.routers.goal_router import router as goal_router
from ..api.routers.interview_router import router as interview_router, abet_interview_router
from ..api.routers.assessment_router import router as assessment_router
from ..api.routers.reports import router as report_router
from ..api.routers.abet_router import router as abet_router
from ..api.routers.multiuser import router as multiuser_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize the framework once at startup.
    """

    framework = get_framework()

    app.state.framework = framework

    yield

    # Future:
    # framework.shutdown()
    # close database connections
    # close vector stores
    # close LLM clients


app = FastAPI(
    title="Adaptive AI Interview Framework",
    description=(
        "Goal-based adaptive oral assessment framework "
        "supporting knowledge-driven interview generation, "
        "adaptive questioning, and research analytics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------

app.include_router(
    knowledge_router,
    prefix="/knowledge",
    tags=["Knowledge"],
)

app.include_router(
    goal_router,
    prefix="/goals",
    tags=["Goals"],
)

app.include_router(
    interview_router,
    prefix="/interviews",
    tags=["Interviews"],
)
app.include_router(abet_interview_router)

app.include_router(
    assessment_router,
    prefix="/assessments",
    tags=["Assessments"],
)

app.include_router(
    report_router,
    prefix="/reports",
    tags=["Reports"],
)

app.include_router(abet_router)
app.include_router(multiuser_router)


@app.get("/")
def root():
    return {
        "name": "Adaptive AI Interview Framework",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }