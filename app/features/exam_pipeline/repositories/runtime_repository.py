"""
repositories/runtime_repository.py

Repository interface for persisting AssessmentContext objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..interview.context import AssessmentContext


class RuntimeRepository(ABC):
    """
    Repository for interview execution state.

    The repository persists AssessmentContext, allowing
    interviews to be paused and resumed.
    """

    @abstractmethod
    def save(
        self,
        context: AssessmentContext,
    ) -> None:
        """
        Persist the current assessment context.
        """
        raise NotImplementedError

    @abstractmethod
    def load(
        self,
        session_id: str,
    ) -> AssessmentContext | None:
        """
        Load a previously saved assessment context.

        Returns None if the session does not exist.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        session_id: str,
    ) -> None:
        """
        Remove persisted runtime state.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(
        self,
        session_id: str,
    ) -> bool:
        """
        Returns True if runtime state exists.
        """
        raise NotImplementedError