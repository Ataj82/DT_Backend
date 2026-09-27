"""
app/repositories/memory/memory_goal_repository.py

In-memory implementation of GoalRepository.

Stores complete GoalModel aggregates.
"""

from __future__ import annotations

from ..goal_repository import GoalRepository
from ...goals.models import GoalModel


class MemoryGoalRepository(GoalRepository):
    """
    Simple in-memory repository for GoalModel objects.
    """

    def __init__(self) -> None:
        self._storage: dict[str, GoalModel] = {}

    # ==========================================================
    # Commands
    # ==========================================================

    def save(
        self,
        goal_model: GoalModel,
    ) -> None:
        """
        Create or update a GoalModel.
        """

        self._storage[goal_model.id] = goal_model
    # ==========================================================
    # Queries
    # ==========================================================

    def get(
        self,
        goal_model_id: str,
    ) -> GoalModel | None:
        """
        Retrieve a GoalModel.
        """

        return self._storage.get(goal_model_id)

    def list(
        self,
    ) -> list[GoalModel]:
        """
        Return all stored GoalModels.
        """

        return list(self._storage.values())

    def exists(
        self,
        goal_model_id: str,
    ) -> bool:
        """
        Check whether a GoalModel exists.
        """

        return goal_model_id in self._storage

    # ==========================================================
    # Delete
    # ==========================================================

    def delete(
        self,
        goal_model_id: str,
    ) -> None:
        """
        Delete a GoalModel.
        """

        self._storage.pop(
            goal_model_id,
            None,
        )

    def clear(
        self,
    ) -> None:
        """
        Remove every GoalModel.
        """

        self._storage.clear()