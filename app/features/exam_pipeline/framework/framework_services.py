"""
framework/framework_services.py

Aggregates all application services required by the
AssessmentFramework.

This object acts as the application's service container.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..services.knowledge_service import KnowledgeService
from ..services.goal_service import GoalService
from ..services.interview_service import InterviewService
from ..services.assessment_service import AssessmentService
from ..reports.report_service import ReportService
from ..abet.service import ABETService
from ..multiuser.service import MultiUserService


@dataclass(slots=True)
class FrameworkServices:
    """
    Collection of application services.

    Instead of injecting many services individually,
    the framework receives this single object.
    """

    knowledge_service: KnowledgeService

    goal_service: GoalService

    interview_service: InterviewService

    assessment_service: AssessmentService

    report_service: ReportService
    abet_service: ABETService
    multi_user_service: MultiUserService
