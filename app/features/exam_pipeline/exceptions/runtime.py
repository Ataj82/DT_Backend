"""
Runtime exceptions.
"""

from .base import AssessmentFrameworkError


class RuntimeError(
    AssessmentFrameworkError,
):
    pass


class RuntimeNotFound(
    RuntimeError,
):
    default_message = (
        "Runtime not found."
    )


class ContextCreationError(
    RuntimeError,
):
    default_message = (
        "Failed to create assessment context."
    )


class RuntimeInitializationError(
    RuntimeError,
):
    default_message = (
        "Failed to initialize runtime."
    )