"""
Assessment exceptions.
"""

from .base import AssessmentFrameworkError


class AssessmentError(
    AssessmentFrameworkError,
):
    pass


class AssessmentFailed(
    AssessmentError,
):
    default_message = (
        "Assessment failed."
    )


class QuestionGenerationError(
    AssessmentError,
):
    default_message = (
        "Question generation failed."
    )


class EvaluationError(
    AssessmentError,
):
    default_message = (
        "Answer evaluation failed."
    )