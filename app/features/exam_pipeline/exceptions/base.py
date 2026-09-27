"""
Base exception hierarchy.
"""

from __future__ import annotations


class AssessmentFrameworkError(Exception):
    """
    Base class for every framework exception.
    """

    default_message = "Assessment framework error."

    def __init__(
        self,
        message: str | None = None,
    ):

        super().__init__(
            message or self.default_message
        )

        self.message = (
            message or self.default_message
        )