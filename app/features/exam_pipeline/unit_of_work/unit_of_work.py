"""
app/unit_of_work/unit_of_work.py

Abstract Unit of Work.

Coordinates repositories participating in a single transaction.

The concrete UnitOfWork implementation is responsible for creating
and managing repository instances and for implementing commit and
rollback behavior.

This class contains no domain or application business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Type

from ..repositories.goal_repository import GoalRepository
from ..repositories.knowledge_repository import KnowledgeRepository
from ..repositories.session_repository import SessionRepository


class UnitOfWork(ABC):
    """
    Abstract Unit of Work.

    A UnitOfWork groups repository operations into a transaction.

    Repositories
    ------------
    knowledge:
        Repository for KnowledgeBase aggregates.

    goals:
        Repository for GoalModel aggregates.

    sessions:
        Repository for InterviewSession aggregates.

    Concrete implementations decide how data is actually persisted.
    """

    knowledge: KnowledgeRepository
    goals: GoalRepository
    sessions: SessionRepository

    # ==========================================================
    # Context manager
    # ==========================================================

    def __enter__(self) -> UnitOfWork:
        """
        Enter the unit-of-work context.

        Returns
        -------
        UnitOfWork
            The active unit of work.
        """

        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Complete or roll back the transaction.

        Successful operations are committed.

        Operations that raise an exception are rolled back.

        Exceptions are deliberately not suppressed.
        """

        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    # ==========================================================
    # Transaction
    # ==========================================================

    @abstractmethod
    def commit(self) -> None:
        """
        Persist the current transaction.
        """

        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """
        Roll back the current transaction.
        """

        raise NotImplementedError