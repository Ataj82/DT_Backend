"""
Knowledge exceptions.
"""

from .base import AssessmentFrameworkError


class KnowledgeError(
    AssessmentFrameworkError,
):
    pass


class KnowledgeNotFound(
    KnowledgeError,
):
    default_message = (
        "Knowledge base not found."
    )


class KnowledgeAlreadyExists(
    KnowledgeError,
):
    default_message = (
        "Knowledge base already exists."
    )


class InvalidKnowledge(
    KnowledgeError,
):
    default_message = (
        "Invalid knowledge base."
    )