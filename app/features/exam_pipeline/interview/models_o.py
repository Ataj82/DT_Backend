"""
app/interview/models.py

Interview domain models.

InterviewSession is the persistent source of truth for an
assessment interview. Every request reconstructs an
AssessmentRuntime from this session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..conversation.history import ConversationHistory


@dataclass(slots=True)
class InterviewSession:
    """
    Persistent interview session.

    All interview state is stored here.

    AssessmentRuntime is disposable.
    """

    # ==========================================================
    # Identity
    # ==========================================================

    student_id: str

    configuration: Any

    knowledge_model: Any

    goal_model: Any

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    # ==========================================================
    # Runtime State
    # ==========================================================

    goal_states: dict[str, Any] = field(
        default_factory=dict
    )

    history: ConversationHistory = field(
        default_factory=ConversationHistory
    )

    events: list[Any] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ==========================================================
    # Progress
    # ==========================================================

    current_goal_id: str | None = None

    current_indicator_id: str | None = None

    completed: bool = False

    # ==========================================================
    # Timing
    # ==========================================================

    started_at: datetime = field(
        default_factory=datetime.utcnow
    )

    finished_at: datetime | None = None

    # ==========================================================
    # Helpers
    # ==========================================================

    def get_goal_state(
        self,
        goal_id: str,
    ):

        return self.goal_states.get(goal_id)

    def add_goal_state(
        self,
        goal_state,
    ) -> None:

        self.goal_states[
            goal_state.goal.id
        ] = goal_state

    def add_event(
        self,
        event,
    ) -> None:

        self.events.append(event)

    def mark_completed(
        self,
    ) -> None:

        self.completed = True

        self.finished_at = datetime.utcnow()

    @property
    def current_goal_state(self):

        if self.current_goal_id is None:
            return None

        return self.goal_states.get(
            self.current_goal_id
        )

    @property
    def turn_count(self) -> int:

        return len(self.history.turns)

    @property
    def last_turn(self):

        return self.history.last