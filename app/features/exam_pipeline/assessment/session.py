"""
interview/interview_session.py

Aggregate root representing one interview session.

The InterviewSession owns all mutable runtime state during an
interview.

Responsibilities
----------------
- Track interview lifecycle
- Own GoalState objects
- Track current goal
- Store conversation history
- Provide navigation between goals

It deliberately does NOT:
- evaluate answers
- compute mastery
- compute coverage
- generate questions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from typing import Any

from ..assessment.goal_state import GoalState


@dataclass(slots=True)
class InterviewSession:
    """
    Aggregate root for a single interview.
    """

    goal_states: list[GoalState]

    id: str = field(default_factory=lambda: str(uuid4()))

    started_at: datetime = field(default_factory=datetime.utcnow)

    completed_at: datetime | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    conversation_history: list[Any] = field(default_factory=list)

    _current_goal_index: int = field(default=0, init=False)

    _completed: bool = field(default=False, init=False)

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def current_goal_state(self) -> GoalState | None:
        if self.finished():
            return None

        return self.goal_states[self._current_goal_index]

    @property
    def current_goal(self):
        state = self.current_goal_state

        if state is None:
            return None

        return state.goal

    @property
    def current_indicator(self):
        state = self.current_goal_state

        if state is None:
            return None

        return state.current_indicator

    @property
    def total_goals(self) -> int:
        return len(self.goal_states)

    @property
    def completed_goals(self) -> int:
        return self._current_goal_index

    # ---------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------

    def advance_goal(self):
        """
        Advance to the next goal.
        """

        if self.finished():
            return None

        self._current_goal_index += 1

        # Navigation alone must never finalize the interview lifecycle.
        # The runtime owns the terminal transition and will mark the
        # session completed only when it receives a terminal
        # ConversationTurn (or an explicit finish decision).
        if self.finished():
            return None

        return self.current_goal

    def reset(self):
        """
        Reset the session.
        """

        self._current_goal_index = 0
        self._completed = False
        self.completed_at = None

        self.conversation_history.clear()

        for goal_state in self.goal_states:
            goal_state.reset()

    # ---------------------------------------------------------
    # Conversation
    # ---------------------------------------------------------

    def add_turn(self, turn):
        """
        Append a conversation turn.

        A turn is expected to be a ConversationTurn domain object.
        """
        self.conversation_history.append(turn)

    @property
    def turns(self):
        return tuple(self.conversation_history)

    @property
    def turn_count(self):
        return len(self.conversation_history)

    # ---------------------------------------------------------
    # Lookup
    # ---------------------------------------------------------

    def get_goal_state(
        self,
        goal_id: str,
    ) -> GoalState | None:

        for state in self.goal_states:

            if state.goal.id == goal_id:
                return state

        return None

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    def finished(self) -> bool:
        return self._current_goal_index >= len(
            self.goal_states
        )

    def progress(self) -> float:
        """
        Interview progress.

        Returns
        -------
        float
            Value in [0,1]
        """

        if not self.goal_states:
            return 1.0

        return self._current_goal_index / len(
            self.goal_states
        )

    def mark_completed(self):
        """
        Mark interview as completed.
        """

        self._completed = True

        if self.completed_at is None:
            self.completed_at = datetime.utcnow()

    def mark_active(self):
        """
        Mark the interview as actively in progress.

        This is the inverse lifecycle operation of ``mark_completed``.
        It is intentionally independent from goal pass/fail state: a
        goal may be resolved while the interview still has remaining
        goals/questions.
        """

        self._completed = False
        self.completed_at = None

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    def set_metadata(
        self,
        key: str,
        value: Any,
    ):
        self.metadata[key] = value

    def get_metadata(
        self,
        key: str,
        default=None,
    ):
        return self.metadata.get(
            key,
            default,
        )

    # ---------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------

    def __len__(self):
        return len(self.goal_states)

    def __iter__(self):
        return iter(self.goal_states)

    def __repr__(self):
        return (
            f"InterviewSession("
            f"id={self.id!r}, "
            f"goals={len(self.goal_states)}, "
            f"current={self._current_goal_index}, "
            f"completed={self.completed})"
        )