"""
repositories/memory_runtime_repository.py

In-memory implementation of RuntimeRepository.

Useful for testing and development.
"""

from __future__ import annotations

from copy import deepcopy
from ...interview.context import AssessmentContext
from ...repositories.runtime_repository import RuntimeRepository


class MemoryRuntimeRepository(RuntimeRepository):

    def __init__(self):

        self._contexts: dict[str, AssessmentContext] = {}

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    def save(
        self,
        context: AssessmentContext,
    ) -> None:

        session_id = context.session.id

        self._contexts[session_id] = deepcopy(context)

    # ---------------------------------------------------------
    # Load
    # ---------------------------------------------------------

    def load(
        self,
        session_id: str,
    ) -> AssessmentContext | None:

        context = self._contexts.get(session_id)

        if context is None:
            return None

        return deepcopy(context)

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def delete(
        self,
        session_id: str,
    ) -> None:

        self._contexts.pop(session_id, None)

    # ---------------------------------------------------------
    # Exists
    # ---------------------------------------------------------

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return session_id in self._contexts