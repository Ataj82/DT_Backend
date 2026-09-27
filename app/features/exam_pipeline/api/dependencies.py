"""
FastAPI dependency providers.
"""

from __future__ import annotations

from functools import lru_cache

from ..framework.assessment_framework import (
    AssessmentFramework,
)
from ..framework.framework_builder import (
    FrameworkBuilder,
)


@lru_cache(maxsize=1)
def get_framework() -> AssessmentFramework:
    """
    Returns the singleton framework.
    """

    return FrameworkBuilder().build()


def get_knowledge_service():
    return get_framework().services.knowledge_service


def get_goal_service():
    return get_framework().services.goal_service


def get_interview_service():
    return get_framework().services.interview_service


def get_assessment_service():
    return get_framework().services.assessment_service


def get_report_service():
    return get_framework().services.report_service