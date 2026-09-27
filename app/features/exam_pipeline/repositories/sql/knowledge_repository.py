from __future__ import annotations

from ..repositories.knowledge_repository import KnowledgeRepository


class SqlKnowledgeRepository(KnowledgeRepository):
    """
    SQL implementation of KnowledgeRepository.

    This repository will be completed once a database
    provider (SQLite/PostgreSQL) is configured.
    """

    def __init__(self, session):
        self._session = session

    def add(self, knowledge):
        raise NotImplementedError

    def get(self, knowledge_id):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def update(self, knowledge):
        raise NotImplementedError

    def delete(self, knowledge_id):
        raise NotImplementedError