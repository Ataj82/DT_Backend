"""
app/navigation/interview_navigator.py

Deterministic navigation coordinator for one assessment interview.

InterviewNavigator coordinates:

    GoalManager
        owns goal position

    EvidencePlanner
        selects the next indicator

    GoalState
        owns indicator runtime state

    AssessmentContext
        mirrors active runtime navigation state

The navigator does NOT own:

- assessment
- scoring
- mastery calculation
- evidence evaluation
- question generation
- persistence
- interview result construction

Important semantic rule
-----------------------

A goal being exhausted is NOT the same as the interview being
complete.

A goal may be:

    PASSED
    FAILED / EXHAUSTED

Both are terminal goal states.

The interview is complete only when GoalManager has no remaining
goals.

Navigation state is therefore kept separate from assessment state.
"""

from __future__ import annotations

from typing import Any

from ..interview.context import AssessmentContext


class InterviewNavigator:
    """
    Coordinate goal and indicator navigation.

    Source-of-truth rules
    ---------------------

    GoalManager
        Source of truth for current goal position.

    GoalState
        Source of truth for current indicator runtime state.

    EvidencePlanner
        Source of truth for indicator selection.

    AssessmentContext
        Runtime mirror of active goal/indicator.

    InterviewNavigator
        Coordinates the above objects without maintaining a second
        navigation index.
    """

    def __init__(
        self,
        *,
        goal_manager,
        evidence_planner,
    ) -> None:
        if goal_manager is None:
            raise ValueError(
                "InterviewNavigator requires a goal_manager."
            )

        if evidence_planner is None:
            raise ValueError(
                "InterviewNavigator requires an evidence_planner."
            )

        self.goal_manager = goal_manager
        self.evidence_planner = evidence_planner

    # ==========================================================
    # Goal access
    # ==========================================================

    def current_goal(
        self,
        context: AssessmentContext | None = None,
    ):
        """
        Return the active goal from GoalManager.

        Supports:

            goal_manager.current_goal

        and legacy:

            goal_manager.current_goal()
        """

        value = getattr(
            self.goal_manager,
            "current_goal",
            None,
        )

        if callable(value):
            value = value()

        return value

    def current_goal_state(
        self,
        context: AssessmentContext | None = None,
    ):
        """
        Return the GoalState belonging to the active goal.

        Preferred source:

            goal_manager.current_goal_state

        Compatibility fallback:

            session.get_goal_state(goal_id)
        """

        state = getattr(
            self.goal_manager,
            "current_goal_state",
            None,
        )

        if callable(state):
            state = state()

        if state is not None:
            return state

        if context is None:
            return None

        goal = self.current_goal(context)

        if goal is None:
            return None

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return None

        getter = getattr(
            session,
            "get_goal_state",
            None,
        )

        if not callable(getter):
            return None

        goal_id = self._normalize_id(
            getattr(goal, "id", None)
        )

        if goal_id is None:
            return None

        return getter(goal_id)

    # ==========================================================
    # Indicator access
    # ==========================================================

    def current_indicator(
        self,
        context: AssessmentContext | None = None,
    ):
        """
        Return the active runtime indicator.

        GoalState is authoritative.
        """

        goal_state = self.current_goal_state(context)

        if goal_state is None:
            return None

        indicator_id = self._normalize_id(
            getattr(
                goal_state,
                "current_indicator_id",
                None,
            )
        )

        if indicator_id is not None:
            indicator = self._get_indicator(
                goal_state,
                indicator_id,
            )

            if indicator is not None:
                return indicator

        legacy_indicator = getattr(
            goal_state,
            "current_indicator",
            None,
        )

        if legacy_indicator is not None:
            return legacy_indicator

        if context is None:
            return None

        context_indicator_id = self._normalize_id(
            getattr(
                context,
                "current_indicator_id",
                None,
            )
        )

        if context_indicator_id is None:
            return None

        return self._get_indicator(
            goal_state,
            context_indicator_id,
        )

    def next_indicator(
        self,
        context: AssessmentContext | None = None,
        *,
        preferred: list[str] | None = None,
    ):
        """
        Select and activate the next indicator.

        Flow:

            GoalState
                ↓
            EvidencePlanner
                ↓
            selected ID
                ↓
            GoalState validation
                ↓
            GoalState activation
                ↓
            context synchronization
                ↓
            runtime IndicatorState
        """

        goal_state = self.current_goal_state(context)

        if goal_state is None:
            return None

        if self._goal_is_resolved(goal_state):
            return None

        selected = self._select_indicator(
            goal_state=goal_state,
            preferred=preferred,
        )

        indicator_id = self._resolve_indicator_id(selected)

        if indicator_id is None:
            return None

        indicator = self._get_indicator(
            goal_state,
            indicator_id,
        )

        if indicator is None:
            raise RuntimeError(
                "EvidencePlanner selected unknown indicator "
                f"'{indicator_id}'."
            )

        self._activate_indicator(
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        self._synchronize_indicator_context(
            context=context,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )

        return indicator

    @staticmethod
    def _goal_is_resolved(goal_state) -> bool:
        resolved = getattr(
            goal_state,
            "resolved",
            False,
        )

        if callable(resolved):
            resolved = resolved()

        if bool(resolved):
            return True

        is_resolved = getattr(
            goal_state,
            "is_resolved",
            False,
        )

        if callable(is_resolved):
            is_resolved = is_resolved()

        return bool(is_resolved)

    def _select_indicator(
        self,
        *,
        goal_state,
        preferred: list[str] | None,
    ):
        selector = getattr(
            self.evidence_planner,
            "select_next_indicator",
            None,
        )

        if not callable(selector):
            raise AttributeError(
                "EvidencePlanner must provide "
                "'select_next_indicator()'."
            )

        if preferred is None:
            return selector(goal_state)

        try:
            return selector(
                goal_state,
                preferred=preferred,
            )
        except TypeError as exc:
            try:
                return selector(goal_state)
            except TypeError:
                raise exc

    # ==========================================================
    # Goal progression
    # ==========================================================

    def advance_goal(
        self,
        context: AssessmentContext,
    ):
        """
        Advance GoalManager to the next goal.

        This method performs navigation only.

        It does not decide whether the previous goal passed or
        failed.
        """

        if context is None:
            raise ValueError(
                "InterviewNavigator.advance_goal requires "
                "an AssessmentContext."
            )

        next_state = self._advance_goal_manager()

        self._reset_current_indicator(context)

        if next_state is None:
            self._synchronize_no_current_goal(context)
            return None

        next_goal = self._extract_goal(next_state)

        if next_goal is None:
            raise RuntimeError(
                "GoalManager returned an object without "
                "a goal definition."
            )

        goal_id = self._normalize_id(
            getattr(next_goal, "id", None)
        )

        if goal_id is None:
            raise RuntimeError(
                "GoalManager returned a goal without an id."
            )

        self._synchronize_goal_context(
            context=context,
            goal_id=goal_id,
        )

        self._mark_context_active(context)

        return next_goal

    @staticmethod
    def _extract_goal(state_or_goal):
        """
        Normalize GoalManager output.

        Preferred:

            GoalState.goal

        Compatibility:

            Goal object directly
        """

        goal = getattr(
            state_or_goal,
            "goal",
            None,
        )

        if goal is not None:
            return goal

        if getattr(
            state_or_goal,
            "id",
            None,
        ) is not None:
            return state_or_goal

        return None

    def _advance_goal_manager(self):
        advance = getattr(
            self.goal_manager,
            "advance",
            None,
        )

        if callable(advance):
            return advance()

        legacy_advance = getattr(
            self.goal_manager,
            "advance_goal",
            None,
        )

        if callable(legacy_advance):
            return legacy_advance()

        raise AttributeError(
            "GoalManager must provide either "
            "'advance()' or 'advance_goal()'."
        )

    # ==========================================================
    # Completion / status
    # ==========================================================

    def has_current_goal(
        self,
        context: AssessmentContext | None = None,
    ) -> bool:
        return self.current_goal(context) is not None

    def finished(
        self,
        context: AssessmentContext,
    ) -> bool:
        """
        Return True only when GoalManager has exhausted all goals.

        IMPORTANT
        ---------
        Interview lifecycle state is deliberately NOT consulted here.
        ``session.completed`` / ``context.interview_completed`` describe
        the conversation lifecycle and can be stale while a runtime is
        reconstructing or advancing a session.  Using either value here
        can incorrectly convert a non-terminal question into a terminal
        interview, which is exactly the Turn-2/Turn-3 failure mode.

        GoalManager is the sole navigation source of truth.
        """

        if context is None:
            raise ValueError(
                "InterviewNavigator.finished requires "
                "an AssessmentContext."
            )

        manager_finished = getattr(
            self.goal_manager,
            "finished",
            None,
        )

        if not callable(manager_finished):
            raise AttributeError(
                "GoalManager must provide 'finished()'."
            )

        return bool(manager_finished())

    @staticmethod
    def _context_is_finished(
        context: AssessmentContext,
    ) -> bool:
        value = getattr(
            context,
            "is_finished",
            False,
        )

        if callable(value):
            value = value()

        if bool(value):
            return True

        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return False

        completed = getattr(
            session,
            "completed",
            False,
        )

        if callable(completed):
            completed = completed()

        return bool(completed)

    # ==========================================================
    # Reset
    # ==========================================================

    def reset(
        self,
        context: AssessmentContext,
    ) -> None:
        """
        Reset navigation position.

        Assessment evidence and GoalState mastery are untouched.
        """

        if context is None:
            raise ValueError(
                "InterviewNavigator.reset requires "
                "an AssessmentContext."
            )

        reset = getattr(
            self.goal_manager,
            "reset",
            None,
        )

        if not callable(reset):
            raise AttributeError(
                "GoalManager must provide 'reset()'."
            )

        reset()

        self._reset_current_indicator(context)

        first_goal = self.current_goal(context)

        if first_goal is None:
            self._synchronize_no_current_goal(context)
            return

        goal_id = self._normalize_id(
            getattr(first_goal, "id", None)
        )

        if goal_id is None:
            raise RuntimeError(
                "Cannot reset navigation: first goal "
                "does not have an id."
            )

        self._synchronize_goal_context(
            context=context,
            goal_id=goal_id,
        )

        self._mark_context_active(context)

    # ==========================================================
    # Indicator helpers
    # ==========================================================

    @staticmethod
    def _resolve_indicator_id(
        selected: Any,
    ) -> str | None:
        if selected is None:
            return None

        if isinstance(selected, str):
            return InterviewNavigator._normalize_id(selected)

        return InterviewNavigator._normalize_id(
            getattr(selected, "id", None)
        )

    @staticmethod
    def _normalize_id(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()

        return normalized or None

    @classmethod
    def _get_indicator(
        cls,
        goal_state,
        indicator_id: str,
    ):
        getter = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(getter):
            indicator = getter(indicator_id)

            if indicator is not None:
                return indicator

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if indicators is None:
            return None

        mapping_get = getattr(
            indicators,
            "get",
            None,
        )

        if callable(mapping_get):
            indicator = mapping_get(indicator_id)

            if indicator is not None:
                return indicator

        items = getattr(
            indicators,
            "items",
            None,
        )

        if callable(items):
            normalized_target = str(indicator_id).strip()

            for key, value in items():
                if str(key).strip() == normalized_target:
                    return value

        return None

    @staticmethod
    def _activate_indicator(
        *,
        goal_state,
        indicator_id: str,
    ) -> None:
        setter = getattr(
            goal_state,
            "set_current_indicator",
            None,
        )

        if callable(setter):
            setter(indicator_id)
            return

        if hasattr(
            goal_state,
            "current_indicator_id",
        ):
            goal_state.current_indicator_id = indicator_id
            return

        raise AttributeError(
            "GoalState must provide either "
            "'set_current_indicator()' or "
            "'current_indicator_id'."
        )

    # ==========================================================
    # Context synchronization
    # ==========================================================

    @classmethod
    def _synchronize_indicator_context(
        cls,
        *,
        context,
        goal_state,
        indicator_id: str,
    ) -> None:
        if context is None:
            return

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        if goal is None:
            raise RuntimeError(
                "Cannot synchronize indicator: "
                "GoalState has no goal."
            )

        goal_id = cls._normalize_id(
            getattr(goal, "id", None)
        )

        if goal_id is None:
            raise RuntimeError(
                "Cannot synchronize indicator: "
                "goal has no id."
            )

        context.current_goal_id = goal_id
        context.current_indicator_id = indicator_id

        cls._synchronize_session(
            context=context,
            goal_id=goal_id,
            indicator_id=indicator_id,
        )

    @classmethod
    def _synchronize_goal_context(
        cls,
        *,
        context,
        goal_id: str,
    ) -> None:
        context.current_goal_id = goal_id
        context.current_indicator_id = None

        cls._synchronize_session(
            context=context,
            goal_id=goal_id,
            indicator_id=None,
        )

    @staticmethod
    def _synchronize_session(
        *,
        context,
        goal_id: str | None,
        indicator_id: str | None,
    ) -> None:
        session = getattr(
            context,
            "session",
            None,
        )

        if session is None:
            return

        if hasattr(session, "current_goal_id"):
            session.current_goal_id = goal_id

        if hasattr(session, "current_indicator_id"):
            session.current_indicator_id = indicator_id

    @classmethod
    def _synchronize_no_current_goal(
        cls,
        context: AssessmentContext,
    ) -> None:
        context.current_goal_id = None
        context.current_indicator_id = None

        cls._synchronize_session(
            context=context,
            goal_id=None,
            indicator_id=None,
        )

        cls._mark_context_completed(context)

    @staticmethod
    def _reset_current_indicator(
        context: AssessmentContext,
    ) -> None:
        reset = getattr(
            context,
            "reset_current_indicator",
            None,
        )

        if callable(reset):
            reset()
        elif hasattr(
            context,
            "current_indicator_id",
        ):
            context.current_indicator_id = None

        session = getattr(
            context,
            "session",
            None,
        )

        if session is not None and hasattr(
            session,
            "current_indicator_id",
        ):
            session.current_indicator_id = None

    # ==========================================================
    # Context lifecycle
    # ==========================================================

    @staticmethod
    def _mark_context_completed(
        context: AssessmentContext,
    ) -> None:
        marker = getattr(
            context,
            "mark_completed",
            None,
        )

        if callable(marker):
            marker()
            return

        if hasattr(
            context,
            "interview_completed",
        ):
            context.interview_completed = True

    @staticmethod
    def _mark_context_active(
        context: AssessmentContext,
    ) -> None:
        marker = getattr(
            context,
            "mark_active",
            None,
        )

        if callable(marker):
            marker()
            return

        if hasattr(
            context,
            "interview_completed",
        ):
            context.interview_completed = False