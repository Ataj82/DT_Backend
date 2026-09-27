"""
Interview exceptions.
"""

from .base import AssessmentFrameworkError


class InterviewError(
    AssessmentFrameworkError,
):
    pass


class InterviewNotFound(
    InterviewError,
):
    default_message = (
        "Interview not found."
    )


class InterviewCompleted(
    InterviewError,
):
    default_message = (
        "Interview has already completed."
    )


class InvalidInterviewState(
    InterviewError,
):
    default_message = (
        "Invalid interview state."
    )