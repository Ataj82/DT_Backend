"""
FastAPI exception handlers.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from .assessment import AssessmentError
from .base import AssessmentFrameworkError
from .goals import GoalNotFound, GoalModelNotFound
from .interview import (
    InterviewCompleted,
    InterviewNotFound,
)
from .knowledge import KnowledgeNotFound
from .runtime import RuntimeNotFound


def register_exception_handlers(
    app: FastAPI,
):

    @app.exception_handler(
        KnowledgeNotFound
    )
    async def handle_knowledge(
        request: Request,
        exc: KnowledgeNotFound,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        GoalModelNotFound
    )
    async def handle_goal_model(
        request: Request,
        exc: GoalModelNotFound,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        GoalNotFound
    )
    async def handle_goal(
        request: Request,
        exc: GoalNotFound,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        InterviewNotFound
    )
    async def handle_interview(
        request: Request,
        exc: InterviewNotFound,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        RuntimeNotFound
    )
    async def handle_runtime(
        request: Request,
        exc: RuntimeNotFound,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        InterviewCompleted
    )
    async def handle_completed(
        request: Request,
        exc: InterviewCompleted,
    ):
        return JSONResponse(
            status_code=409,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        AssessmentError
    )
    async def handle_assessment(
        request: Request,
        exc: AssessmentError,
    ):
        return JSONResponse(
            status_code=400,
            content={
                "detail": exc.message,
            },
        )

    @app.exception_handler(
        AssessmentFrameworkError
    )
    async def handle_framework(
        request: Request,
        exc: AssessmentFrameworkError,
    ):
        return JSONResponse(
            status_code=500,
            content={
                "detail": exc.message,
            },
        )