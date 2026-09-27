"""
app/assessment/goal_manager.py

Goal navigation coordinator.

GoalManager is responsible only for traversing the ordered collection
of GoalState objects belonging to an interview.

Responsibilities
----------------
- Track the active goal.
- Advance to the next goal.
- Reset navigation.
- Look up goal state.
- Report navigation progress.
- Restore navigation position when rebuilding runtime state.

Non-responsibilities
--------------------
- Answer evaluation.
- Scoring.
- Evidence evaluation.
- Mastery calculation.
- Confidence calculation.
- Indicator selection.
- Question generation.
- Academic goal completion.
- Interview lifecycle completion.

Important distinction
---------------------
GoalManager tracks NAVIGATION state.

It does not decide whether a goal has academically passed.

Therefore:

    navigation finished
        !=
    all goals mastered
        !=
    assessment passed

Those decisions belong to the assessment layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .goal_state import GoalState


class GoalManager:
    """
    Navigate across an ordered collection of GoalState objects.

    The constructor accepts either:

    1. An iterable of GoalState objects.
    2. An object exposing a ``goals`` property containing GoalState
       objects.

    The manager owns only the navigation cursor.
    """

    def __init__(
        self,
        goal_states: Iterable[GoalState] | Any,
    ) -> None:

        source = self._resolve_source(
            goal_states
        )

        states = self._materialize_states(
            source
        )

        self._validate_goal_states(
            states
        )

        self._goal_states = states

        self._goal_state_by_id = (
            self._build_goal_index(
                states
            )
        )

        self._current_index = (
            self._restore_current_index(
                states,
                goal_states,
            )
        )

    # ==========================================================
    # Construction
    # ==========================================================

    @staticmethod
    def _resolve_source(
        source: Iterable[GoalState] | Any,
    ) -> Iterable[GoalState]:

        if source is None:
            raise TypeError(
                "GoalManager requires goal states; "
                "received None."
            )

        # InterviewSession-like objects may expose ``goals``.
        goals = getattr(
            source,
            "goals",
            None,
        )

        if goals is not None:
            return goals

        return source

    @staticmethod
    def _materialize_states(
        source: Iterable[GoalState],
    ) -> list[GoalState]:

        try:
            return list(source)

        except TypeError as exc:
            raise TypeError(
                "GoalManager requires an iterable of "
                "GoalState objects or an object exposing "
                "a 'goals' property."
            ) from exc

    @staticmethod
    def _validate_goal_states(
        states: list[GoalState],
    ) -> None:

        for index, state in enumerate(
            states
        ):

            if state is None:
                raise TypeError(
                    "GoalManager received None at "
                    f"goal state index {index}."
                )

            goal = getattr(
                state,
                "goal",
                None,
            )

            if goal is None:
                raise TypeError(
                    "GoalManager requires every GoalState "
                    "to reference a goal; "
                    f"index {index} is invalid."
                )

            goal_id = getattr(
                goal,
                "id",
                None,
            )

            if goal_id is None:
                raise TypeError(
                    "GoalManager requires every GoalState "
                    "to reference a goal with an id; "
                    f"index {index} is invalid."
                )

    @staticmethod
    def _build_goal_index(
        states: list[GoalState],
    ) -> dict[str, GoalState]:

        index: dict[str, GoalState] = {}

        for state in states:

            goal = state.goal

            goal_id = str(
                goal.id
            )

            # Preserve existing behavior:
            # first duplicate ID wins.
            if goal_id not in index:
                index[goal_id] = state

        return index

    # ==========================================================
    # State Restoration
    # ==========================================================

    @classmethod
    def _restore_current_index(
        cls,
        states: list[GoalState],
        source: Any,
    ) -> int:

        if not states:
            return 0

        # ------------------------------------------------------
        # 1. Explicit persisted current goal.
        # ------------------------------------------------------

        current_goal_id = getattr(
            source,
            "current_goal_id",
            None,
        )

        if current_goal_id is not None:

            index = cls._find_goal_index(
                states,
                current_goal_id,
            )

            if index is None:
                raise ValueError(
                    "Persisted current_goal_id references "
                    f"unknown goal '{current_goal_id}'."
                )

            return index

        # ------------------------------------------------------
        # 2. Compatibility fallback:
        #    latest conversation turn.
        # ------------------------------------------------------

        last_turn = getattr(
            source,
            "last_turn",
            None,
        )

        if last_turn is None:
            return 0

        goal_id = getattr(
            last_turn,
            "goal_id",
            None,
        )

        if goal_id is None:
            return 0

        index = cls._find_goal_index(
            states,
            goal_id,
        )

        if index is None:
            raise ValueError(
                "Persisted conversation turn references "
                f"unknown goal '{goal_id}'."
            )

        return index

    @staticmethod
    def _find_goal_index(
        states: list[GoalState],
        goal_id: Any,
    ) -> int | None:

        target_id = str(
            goal_id
        )

        for index, state in enumerate(
            states
        ):

            goal = getattr(
                state,
                "goal",
                None,
            )

            if goal is None:
                continue

            candidate_id = getattr(
                goal,
                "id",
                None,
            )

            if (
                candidate_id is not None
                and str(candidate_id) == target_id
            ):
                return index

        return None

    # ==========================================================
    # Current Navigation State
    # ==========================================================

    @property
    def current_index(self) -> int:
        """
        Zero-based index of the active goal.

        When navigation is exhausted:

            current_index == total_goals
        """

        return self._current_index

    @property
    def current_goal_state(
        self,
    ) -> GoalState | None:

        if self.finished():
            return None

        return self._goal_states[
            self._current_index
        ]

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

    # ==========================================================
    # Navigation
    # ==========================================================

    def advance(
        self,
    ) -> GoalState | None:
        """
        Advance navigation by exactly one goal.

        This method DOES NOT mark the previous goal as academically
        completed.

        It only moves the navigation cursor.

        Returns the new active GoalState, or None when navigation
        becomes exhausted.
        """

        if self.finished():
            return None

        self._current_index += 1

        return self.current_goal_state

    def advance_goal(
        self,
    ) -> GoalState | None:
        """
        Backward-compatible alias for advance().
        """

        return self.advance()

    def reset(self) -> None:
        """
        Reset navigation to the first goal.

        Assessment data inside GoalState is untouched.
        """

        self._current_index = 0

    # ==========================================================
    # Goal Lookup
    # ==========================================================

    def get(
        self,
        goal_id: str,
    ) -> GoalState | None:
        """
        Return GoalState for the supplied goal ID.

        Lookup is O(1).
        """

        if goal_id is None:
            return None

        return self._goal_state_by_id.get(
            str(goal_id)
        )

    def get_goal_state(
        self,
        goal_id: str,
    ) -> GoalState | None:

        return self.get(
            goal_id
        )

    # ==========================================================
    # Navigation Status
    # ==========================================================

    def finished(self) -> bool:
        """
        Return True when navigation has exhausted all goals.

        This is a NAVIGATION condition only.

        It does not imply that the goals passed academically.
        """

        return (
            self._current_index
            >= len(self._goal_states)
        )

    @property
    def total_goals(self) -> int:
        return len(
            self._goal_states
        )

    @property
    def completed_goals(self) -> int:
        """
        Number of goals already traversed.

        This is deliberately navigation-based.

        It must not be interpreted as the number of academically
        mastered goals.
        """

        return min(
            max(
                self._current_index,
                0,
            ),
            self.total_goals,
        )

    @property
    def remaining_goals(self) -> int:

        return max(
            0,
            self.total_goals
            - self.completed_goals,
        )

    @property
    def progress(self) -> float:
        """
        Navigation progress in [0.0, 1.0].

        An assessment with no goals is considered fully traversed.
        """

        total = self.total_goals

        if total == 0:
            return 1.0

        return (
            self.completed_goals
            / total
        )

    # ==========================================================
    # Goal Collections
    # ==========================================================

    def all_goal_states(
        self,
    ) -> list[GoalState]:
        """
        Return a copy of all GoalState objects.
        """

        return list(
            self._goal_states
        )

    def remaining_goal_states(
        self,
    ) -> list[GoalState]:

        if self.finished():
            return []

        return list(
            self._goal_states[
                self._current_index:
            ]
        )

    def completed_goal_states(
        self,
    ) -> list[GoalState]:

        if self._current_index <= 0:
            return []

        return list(
            self._goal_states[
                :self._current_index
            ]
        )

    # ==========================================================
    # Convenience
    # ==========================================================

    def has_current_goal(
        self,
    ) -> bool:

        return (
            self.current_goal_state
            is not None
        )

    def is_first_goal(
        self,
    ) -> bool:

        return (
            self.current_index == 0
            and not self.finished()
        )

    def is_last_goal(
        self,
    ) -> bool:

        return (
            self.total_goals > 0
            and self.current_index
            == self.total_goals - 1
        )