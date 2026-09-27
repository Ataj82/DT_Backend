"""
app/interview/interview_session.py

Aggregate root for an interview session.

InterviewSession owns persistent/mutable interview state.

Responsibilities
----------------
- Own GoalState objects.
- Store conversation turns.
- Store interview metadata.
- Manage interview lifecycle.
- Provide goal-state lookup.
- Expose the current persisted goal context.
- Support resetting interview runtime state.

Non-responsibilities
--------------------
- Goal navigation.
- Assessment reasoning.
- Scoring.
- Evidence evaluation.
- Indicator selection.
- Question generation.

Goal navigation is owned by GoalManager / InterviewNavigator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..assessment.goal_state import GoalState
from .conversation_turn import ConversationTurn


# ==========================================================
# Time
# ==========================================================


def _utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp.
    """
    return datetime.now(timezone.utc)


# ==========================================================
# Interview Session
# ==========================================================


@dataclass(slots=True)
class InterviewSession:
    """
    Aggregate root for one interview session.

    InterviewSession owns session state.

    GoalManager owns navigation.
    """

    # ======================================================
    # Identity
    # ======================================================

    id: str

    student_id: str

    # ======================================================
    # Assessment Models
    # ======================================================

    goal_model: Any
    knowledge_model: Any
    configuration: Any

    interviewer_id: str | None = None

    # ======================================================
    # Lifecycle
    # ======================================================

    started_at: datetime = field(
        default_factory=_utc_now
    )

    finished_at: datetime | None = None

    completed: bool = False

    # ======================================================
    # Runtime State
    # ======================================================

    goal_states: dict[str, GoalState] = field(
        default_factory=dict
    )

    # Persisted navigation context.
    #
    # GoalManager reads this value when reconstructing its
    # runtime navigation position.
    current_goal_id: str | None = None

    current_indicator_id: str | None = None

    # ======================================================
    # Conversation
    # ======================================================

    turns: list[ConversationTurn] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ======================================================
    # Initialization
    # ======================================================

    def __post_init__(self) -> None:
        """
        Initialize GoalState objects from the configured goal model.

        Existing GoalState objects are preserved.

        This is important when restoring a persisted session.
        """

        if self.goal_states:
            return

        goals = getattr(
            self.goal_model,
            "goals",
            None,
        )

        if goals is None:
            return

        for goal in goals:
            goal_id = getattr(
                goal,
                "id",
                None,
            )

            if goal_id is None:
                continue

            goal_id = str(goal_id)

            self.goal_states[goal_id] = GoalState(
                goal=goal
            )

    # ======================================================
    # Goal Lookup
    # ======================================================

    def get_goal_state(
        self,
        goal_id: str,
    ) -> GoalState | None:
        """
        Return runtime state for a goal.
        """

        if goal_id is None:
            return None

        return self.goal_states.get(
            str(goal_id)
        )

    @property
    def goals(self) -> list[GoalState]:
        """
        Return GoalState objects in session order.

        GoalManager consumes this property.

        A copy is returned so callers cannot replace the
        session's internal dictionary.
        """

        return list(
            self.goal_states.values()
        )

    # ======================================================
    # Current Goal Context
    # ======================================================

    @property
    def current_goal(self):
        """
        Return the currently persisted goal definition.

        Navigation itself is NOT performed here.
        """

        if self.current_goal_id is None:
            return None

        state = self.get_goal_state(
            self.current_goal_id
        )

        if state is None:
            return None

        return state.goal

    @property
    def current_goal_state(self) -> GoalState | None:
        """
        Return the GoalState corresponding to current_goal_id.
        """

        if self.current_goal_id is None:
            return None

        return self.get_goal_state(
            self.current_goal_id
        )

    @property
    def current_indicator(self):
        """
        Return the currently persisted indicator.

        Indicator selection belongs to the assessment/navigation
        layer. This property only exposes persisted state.
        """

        state = self.current_goal_state

        if state is None:
            return None

        indicator_id = self.current_indicator_id

        if indicator_id is not None:
            get_indicator = getattr(
                state,
                "get_indicator",
                None,
            )

            if callable(get_indicator):
                return get_indicator(
                    indicator_id
                )

        return getattr(
            state,
            "current_indicator",
            None,
        )

    def set_current_goal(
        self,
        goal_id: str | None,
    ) -> None:
        """
        Persist the current goal context.

        GoalManager / InterviewNavigator should normally call this.
        """

        if goal_id is None:
            self.current_goal_id = None
            self.current_indicator_id = None
            return

        goal_id = str(goal_id)

        if goal_id not in self.goal_states:
            raise ValueError(
                f"Unknown goal '{goal_id}'."
            )

        self.current_goal_id = goal_id

        # A goal change invalidates the previous indicator.
        self.current_indicator_id = None

    def set_current_indicator(
        self,
        indicator_id: str | None,
    ) -> None:
        """
        Persist the current indicator context.
        """

        self.current_indicator_id = (
            None
            if indicator_id is None
            else str(indicator_id)
        )

    # ======================================================
    # Conversation
    # ======================================================

    def add_turn(
        self,
        turn: ConversationTurn,
    ) -> None:
        """
        Append a conversation turn.
        """

        self.turns.append(
            turn
        )

    @property
    def last_turn(
        self,
    ) -> ConversationTurn | None:
        """
        Return the latest conversation turn.

        GoalManager uses this as a compatibility fallback when
        restoring navigation state.
        """

        if not self.turns:
            return None

        return self.turns[-1]

    @property
    def turn_count(self) -> int:
        """
        Return the number of conversation turns.
        """

        return len(
            self.turns
        )

    # ======================================================
    # Compatibility: history
    # ======================================================

    @property
    def history(self) -> "_ConversationHistoryView":
        """
        Backward-compatible conversation-history view.

        Supported legacy operations:

            session.history.last
            session.history.turns
            session.history.add(turn)
            session.history.clear()
        """

        return _ConversationHistoryView(
            self
        )

    # ======================================================
    # Lifecycle
    # ======================================================

    def mark_completed(self) -> None:
        """
        Mark the interview as completed.

        The original completion timestamp is preserved.
        """

        self.completed = True

        if self.finished_at is None:
            self.finished_at = _utc_now()

    def mark_active(self) -> None:
        """
        Mark the interview as active because a non-terminal turn exists.

        A newly generated interviewer question is authoritative evidence
        that the interview is still running. This method repairs a stale
        lifecycle flag without touching assessment or navigation state.
        """

        self.completed = False
        self.finished_at = None

    def finish(self) -> None:
        """
        Backward-compatible alias for mark_completed().
        """

        self.mark_completed()

    # ======================================================
    # Reset
    # ======================================================

    def reset(self) -> None:
        """
        Reset interview runtime state.

        Navigation ownership remains with GoalManager.

        Therefore this method resets persisted navigation context,
        but does not attempt to manipulate GoalManager directly.
        """

        # --------------------------------------------------
        # Lifecycle
        # --------------------------------------------------

        self.started_at = _utc_now()
        self.finished_at = None
        self.completed = False

        # --------------------------------------------------
        # Navigation context
        # --------------------------------------------------

        self.current_goal_id = None
        self.current_indicator_id = None

        # --------------------------------------------------
        # Conversation
        # --------------------------------------------------

        self.turns.clear()

        # --------------------------------------------------
        # Goal runtime state
        # --------------------------------------------------

        for goal_id, state in list(
            self.goal_states.items()
        ):
            reset = getattr(
                state,
                "reset",
                None,
            )

            if callable(reset):
                reset()
                continue

            # Compatibility with older GoalState implementations.
            self.goal_states[goal_id] = GoalState(
                goal=state.goal
            )

    # ======================================================
    # Metadata
    # ======================================================

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Store session metadata.
        """

        self.metadata[key] = value

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve session metadata.
        """

        return self.metadata.get(
            key,
            default,
        )

    def set_metadata(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Compatibility alias for set().
        """

        self.set(
            key,
            value,
        )

    def get_metadata(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Compatibility alias for get().
        """

        return self.get(
            key,
            default,
        )

    # ======================================================
    # Factory
    # ======================================================

    @classmethod
    def create(
        cls,
        *,
        student_id: str,
        goal_model,
        knowledge_model,
        configuration,
        interviewer_id: str | None = None,
    ) -> "InterviewSession":
        """
        Create a new InterviewSession.

        GoalState objects are initialized automatically.
        """

        session = cls(
            id=str(uuid4()),
            student_id=student_id,
            goal_model=goal_model,
            knowledge_model=knowledge_model,
            configuration=configuration,
            interviewer_id=interviewer_id,
        )

        # --------------------------------------------------
        # Initialize persisted current goal.
        #
        # GoalManager remains responsible for navigation,
        # but a new session needs an initial navigation anchor.
        # --------------------------------------------------

        if session.goal_states:
            session.current_goal_id = next(
                iter(session.goal_states)
            )

        return session


# ==========================================================
# Conversation History Compatibility View
# ==========================================================


class _ConversationHistoryView:
    """
    Compatibility view over InterviewSession.turns.

    Does not own another list.
    """

    __slots__ = (
        "_session",
    )

    def __init__(
        self,
        session: InterviewSession,
    ) -> None:
        self._session = session

    @property
    def turns(
        self,
    ) -> list[ConversationTurn]:
        return self._session.turns

    @property
    def last(
        self,
    ) -> ConversationTurn | None:
        return self._session.last_turn

    def add(
        self,
        turn: ConversationTurn,
    ) -> None:
        self._session.add_turn(
            turn
        )

    def clear(self) -> None:
        self._session.turns.clear()

    def __len__(self) -> int:
        return len(
            self._session.turns
        )

    def __iter__(self):
        return iter(
            self._session.turns
        )