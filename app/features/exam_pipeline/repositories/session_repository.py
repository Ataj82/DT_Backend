from __future__ import annotations

from abc import ABC, abstractmethod

from ..interview.interview_session import InterviewSession


class SessionRepository(ABC):
    """
    Repository interface for InterviewSession.
    """

    @abstractmethod
    def save(
        self,
        session: InterviewSession,
    ) -> None:
        ...

    @abstractmethod
    def update(
        self,
        session: InterviewSession,
    ) -> None:
        ...

    @abstractmethod
    def get(
        self,
        session_id: str,
    ) -> InterviewSession:
        ...

    @abstractmethod
    def delete(
        self,
        session_id: str,
    ) -> None:
        ...

    @abstractmethod
    def list(
        self,
    ) -> list[InterviewSession]:
        ...