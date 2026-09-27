"""
Goal exceptions.
"""

from .base import AssessmentFrameworkError


class GoalError(
    AssessmentFrameworkError,
):
    pass


class GoalModelNotFound(
    GoalError,
):
    default_message = (
        "Goal model not found."
    )


class GoalNotFound(
    GoalError,
):
    default_message = (
        "Goal not found."
    )


class GoalGenerationError(
    GoalError,
):
    default_message = (
        "Goal generation failed."
    )