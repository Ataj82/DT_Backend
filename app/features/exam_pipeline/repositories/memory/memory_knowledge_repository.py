"""
app/repositories/memory_knowledge_repository.py

In-memory implementation of KnowledgeRepository.
"""

from __future__ import annotations

from typing import Any
from ..knowledge_repository import KnowledgeRepository
from ...knowledge.models import KnowledgeBase


class MemoryKnowledgeRepository(KnowledgeRepository):
    """
    Simple in-memory repository.

    Intended for development and testing.
    """

    def __init__(self) -> None:
        self._storage: dict[str, KnowledgeBase] = {}

    # ---------------------------------------------------------

    def add(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:

        self._storage[knowledge_base.id] = knowledge_base

    # ---------------------------------------------------------

    def get(
        self,
        knowledge_base_id: str,
    ) -> KnowledgeBase | None:

        return self._storage.get(knowledge_base_id)

    # ---------------------------------------------------------

    def list(
        self,
    ) -> list[KnowledgeBase]:

        return list(self._storage.values())

    # ---------------------------------------------------------

    def update(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:

        if knowledge_base.id not in self._storage:
            raise KeyError(
                f"KnowledgeBase '{knowledge_base.id}' does not exist."
            )

        self._storage[knowledge_base.id] = knowledge_base

    # ---------------------------------------------------------

    def delete(
        self,
        knowledge_base_id: str,
    ) -> None:

        self._storage.pop(
            knowledge_base_id,
            None,
        )

    # ---------------------------------------------------------

    def exists(
        self,
        knowledge_base_id: str,
    ) -> bool:

        return knowledge_base_id in self._storage

    # ---------------------------------------------------------

    def clear(
        self,
    ) -> None:

        self._storage.clear()

    # ---------------------------------------------------------

    def search(
        self,
        *,
        knowledge_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[Any]:
        """
        Very simple full-text search over document contents.
        """

        kb = self.get(knowledge_id)

        if kb is None:
            return []

        query = query.lower()

        results: list[dict[str, Any]] = []

        for document in kb.documents:

            if query in document.content.lower():

                results.append(
                    {
                        "text": document.content,
                        "score": 1.0,
                        "source": document.filename,
                        "metadata": document.metadata,
                    }
                )

        return results[:top_k]