from __future__ import annotations

from ...interview.interview_session import InterviewSession
from ...repositories.session_repository import SessionRepository
from typing import Optional


class MemorySessionRepository(SessionRepository):

    def __init__(self):

        self._sessions: dict[str, InterviewSession] = {}

    # ---------------------------------------------------------

    def save(
        self,
        session: InterviewSession,
    ) -> None:

        self._sessions[session.id] = session

    # ---------------------------------------------------------

    def update(
        self,
        session: InterviewSession,
    ) -> None:

        self._sessions[session.id] = session

    # ---------------------------------------------------------

    def get(
        self,
        session_id: str,
    ) -> Optional[InterviewSession]:

        # Repository queries are intentionally non-throwing.  Application
        # services and API routers use None to distinguish a missing session
        # from an internal failure.  Raising KeyError here turned a stale or
        # missing interview id into an HTTP 500.
        return self._sessions.get(session_id)

    # ---------------------------------------------------------

    def delete(
        self,
        session_id: str,
    ) -> None:

        self._sessions.pop(
            session_id,
            None,
        )

    # ---------------------------------------------------------

    def list(
        self,
    ) -> list[InterviewSession]:

        return list(
            self._sessions.values()
        )