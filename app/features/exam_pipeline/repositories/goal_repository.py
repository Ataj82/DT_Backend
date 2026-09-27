"""
repositories/goal_repository.py

Repository interface for GoalModel persistence.

A GoalModel is the aggregate root of the goal subsystem.
Individual Goal objects are managed through the GoalModel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..goals.models import GoalModel


class GoalRepository(ABC):
    """
    Repository interface for GoalModel persistence.
    """

    @abstractmethod
    def save(
        self,
        goal_model: GoalModel,
    ) -> None:
        """
        Create or update a GoalModel.
        """
        ...

    @abstractmethod
    def get(
        self,
        goal_model_id: str,
    ) -> GoalModel | None:
        """
        Retrieve a GoalModel by its id.
        """
        ...

    @abstractmethod
    def list(
        self,
    ) -> list[GoalModel]:
        """
        Return every stored GoalModel.
        """
        ...

    @abstractmethod
    def delete(
        self,
        goal_model_id: str,
    ) -> None:
        """
        Delete a GoalModel.
        """
        ...

    @abstractmethod
    def exists(
        self,
        goal_model_id: str,
    ) -> bool:
        """
        Check whether a GoalModel exists.
        """
        ...

    @abstractmethod
    def clear(
        self,
    ) -> None:
        """
        Remove all GoalModels.
        """
        ...