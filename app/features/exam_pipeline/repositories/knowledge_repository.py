"""
app/repositories/knowledge_repository.py

Abstract repository interface for KnowledgeBase persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..knowledge.models import KnowledgeBase


class KnowledgeRepository(ABC):
    """
    Persistence contract for KnowledgeBase aggregates.
    """

    @abstractmethod
    def add(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:
        """
        Persist a new knowledge base.
        """
        ...

    @abstractmethod
    def get(
        self,
        knowledge_base_id: str,
    ) -> KnowledgeBase | None:
        """
        Retrieve a knowledge base by id.
        """
        ...

    @abstractmethod
    def list(
        self,
    ) -> list[KnowledgeBase]:
        """
        Return every stored knowledge base.
        """
        ...

    @abstractmethod
    def update(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:
        """
        Persist changes to a knowledge base.
        """
        ...

    @abstractmethod
    def delete(
        self,
        knowledge_base_id: str,
    ) -> None:
        """
        Remove a knowledge base.
        """
        ...

    @abstractmethod
    def exists(
        self,
        knowledge_base_id: str,
    ) -> bool:
        """
        Check whether a knowledge base exists.
        """
        ...

    @abstractmethod
    def clear(
        self,
    ) -> None:
        """
        Remove all knowledge bases.
        """
        ...

    @abstractmethod
    def search(
        self,
        *,
        knowledge_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[Any]:
        """
        Search inside a knowledge base.

        Returns implementation-specific search results.
        """
        ...