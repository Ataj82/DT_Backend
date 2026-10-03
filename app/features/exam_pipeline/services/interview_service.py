"""
app/services/interview_service.py

Application service responsible for interview sessions.
"""

from __future__ import annotations

from ..interview.interview_session import InterviewSession
from ..assessment.runtime_factory import AssessmentRuntimeFactory
from ..unit_of_work.unit_of_work import UnitOfWork
from uuid import uuid4
from threading import RLock
from contextlib import contextmanager

class InterviewService:
    """
    Coordinates interview sessions.

    Assessment logic lives inside AssessmentRuntime.
    """

    def __init__(
        self,
        *,
        runtime_factory: AssessmentRuntimeFactory,
        uow: UnitOfWork,
    ):
        self.runtime_factory = runtime_factory
        self.uow = uow
        # In-memory repositories can otherwise load the same session in two
        # concurrent requests and let the later save overwrite assessment state.
        self._session_locks: dict[str, RLock] = {}
        self._session_locks_guard = RLock()

    @contextmanager
    def session_lock(self, session_id: str):
        """Serialize the complete read -> mutate -> save transaction for one session.

        This is intentionally process-local because the current development
        architecture uses in-memory repositories. Production multi-worker
        deployments should replace this with database transaction/versioning.
        """
        key = str(session_id).strip()
        if not key:
            raise ValueError("session_id cannot be empty.")
        with self._session_locks_guard:
            lock = self._session_locks.get(key)
            if lock is None:
                lock = RLock()
                self._session_locks[key] = lock
        with lock:
            yield

    # ---------------------------------------------------------
    # Session lifecycle
    # ---------------------------------------------------------

    def create_session(
        self,
        *,
        student_id: str,
        knowledge_model,
        goal_model,
        configuration=None,
        interviewer_id: str | None = None,
        session_id: str | None = None,
    ) -> InterviewSession:

        session = InterviewSession(
            id=str(session_id or uuid4()),
            student_id=student_id,
            knowledge_model=knowledge_model,
            goal_model=goal_model,
            configuration=configuration,
            interviewer_id=interviewer_id,
        )

        # Persist the resolved interview language on the session itself.
        # Configuration is the normal source, but session metadata is the
        # immutable runtime fallback used when a later request reconstructs
        # the conversation context. This prevents a Persian session from
        # silently falling back to the global English default after turn 1.
        try:
            from ..language.resolver import normalize_language, resolve_language
            configured_language = normalize_language(
                getattr(configuration, "language", None),
                default=None,
            )
            if not configured_language and knowledge_model:
                configured_language, _ = resolve_language(knowledge=knowledge_model)
            session.metadata["language"] = configured_language or "fa"
        except Exception:
            # Language metadata is additive; never make legacy session
            # creation fail because the optional language helper is absent.
            pass

        with self.uow:

            self.uow.sessions.save(session)

            self.uow.commit()

        return session

    def restore_session(
        self,
        *,
        session_id: str,
        student_id: str,
        knowledge_model,
        goal_model,
        configuration=None,
        interviewer_id: str | None = None,
    ) -> InterviewSession:
        """Restore a missing, never-started session using its assignment snapshot.

        This is deliberately narrower than generic session creation: callers
        should use it only when the enrollment is still ASSIGNED and therefore
        there is no assessment history to overwrite.
        """
        existing = self.get_session(session_id)
        if existing is not None:
            return existing
        return self.create_session(
            student_id=student_id,
            knowledge_model=knowledge_model,
            goal_model=goal_model,
            configuration=configuration,
            interviewer_id=interviewer_id,
            session_id=session_id,
        )

    # ---------------------------------------------------------
    # Runtime
    # ---------------------------------------------------------
    def start_interview(
            self,
            session_id: str,
    ):
        session = self.get_session(
            session_id
        )

        if session is None:
            raise ValueError(
                f"Interview session '{session_id}' not found."
            )

        runtime = self.runtime_factory.create(
            session=session
        )

        # Only reconstruct the runtime here.
        # The caller decides whether it wants the first turn.
        return runtime
############
    def start_interview_o(
        self,
        session_id: str,
    ):

        with self.uow:

            session = self.uow.sessions.get(session_id)

        if session is None:
            raise ValueError(
                f"Interview session '{session_id}' not found."
            )

        return self.runtime_factory.create(session=session)

    # ---------------------------------------------------------
    # Queries
    # ---------------------------------------------------------

    def get_session(
        self,
        session_id: str,
    ) -> InterviewSession | None:

        with self.uow:

            return self.uow.sessions.get(session_id)

    def list_sessions(
        self,
    ) -> list[InterviewSession]:

        with self.uow:

            return list(self.uow.sessions.list())

    # ---------------------------------------------------------
    # Persistence
    # ---------------------------------------------------------

    def save(
        self,
        session: InterviewSession,
    ) -> InterviewSession:

        with self.uow:

            self.uow.sessions.save(session)

            self.uow.commit()

        return session

    def delete(
        self,
        session_id: str,
    ) -> None:

        with self.uow:

            self.uow.sessions.delete(session_id)

            self.uow.commit()