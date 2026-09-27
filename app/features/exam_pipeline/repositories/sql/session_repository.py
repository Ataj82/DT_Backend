from __future__ import annotations

from ..repositories.session_repository import SessionRepository


class SqlSessionRepository(SessionRepository):

    def __init__(self, session):
        self._session = session

    def add(self, session):
        raise NotImplementedError

    def get(self, session_id):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def update(self, session):
        raise NotImplementedError

    def delete(self, session_id):
        raise NotImplementedError