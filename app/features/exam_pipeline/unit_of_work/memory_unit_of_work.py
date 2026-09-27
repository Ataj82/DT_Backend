"""
Memory-backed Unit of Work.
"""

from __future__ import annotations

from .unit_of_work import UnitOfWork

from ..repositories.memory.memory_goal_repository import (
    MemoryGoalRepository,
)

from ..repositories.memory.memory_knowledge_repository import (
    MemoryKnowledgeRepository,
)

from ..repositories.memory.memory_session_repository import (
    MemorySessionRepository,
)


class MemoryUnitOfWork(UnitOfWork):
    """
    In-memory implementation of UnitOfWork.

    Used for development and testing.
    """

    def __init__(
        self,
        *,
        knowledge_repository: MemoryKnowledgeRepository,
        goal_repository: MemoryGoalRepository,
        session_repository: MemorySessionRepository,
    ):

        self.knowledge = knowledge_repository

        self.goals = goal_repository

        self.sessions = session_repository

    # ==========================================================
    # Transaction
    # ==========================================================

    def commit(self) -> None:
        """
        Memory repositories commit immediately.

        Method kept for interface compatibility.
        """
        return None

    def rollback(self) -> None:
        """
        Nothing to rollback for in-memory repositories.

        Method kept for interface compatibility.
        """
        return None