from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from .api.middleware import (
    configure_cors,
    LoggingMiddleware,
    RequestIdMiddleware,
    TimingMiddleware,
)
from .api.routers import (
    knowledge_router,
    goal_router,
    interview_router,
    reports,
    abet_router,
)
from .api.routers import multiuser
from .api.middleware.security_headers import SecurityHeadersMiddleware
from .production.readiness import check_readiness
from .api.dependencies import get_framework
from .exceptions.handlers import (
    register_exception_handlers,
)
framework = get_framework()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.framework = framework

    yield

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
# Middleware
# ---------------------------------------------------------


configure_cors(app)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------
register_exception_handlers(app)
app.include_router(knowledge_router.router)
app.include_router(goal_router.router)
app.include_router(interview_router.router)
# The documented runtime entrypoint is app.main:app, so ABET routes
# must be mounted here as well as in app.api.main.
app.include_router(interview_router.abet_interview_router)
app.include_router(abet_router.router)
app.include_router(multiuser.router)
app.include_router(reports.router)

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["System"])
async def readiness():
    report = check_readiness()
    return {"status": "ready" if report.ready else "not_ready", "ready": report.ready, "checks": report.checks, "warnings": report.warnings}