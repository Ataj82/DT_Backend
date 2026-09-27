"""
interview/interview_context.py

Runtime context for one interview.

InterviewContext is a lightweight object that groups together
the InterviewSession and the long-lived application services.

It owns no business logic.

Responsibilities
----------------
- expose the InterviewSession
- expose GoalManager
- expose application services
"""

from __future__ import annotations

from dataclasses import dataclass

from ..assessment.goal_manager import GoalManager
from .interview_session import InterviewSession


@dataclass(slots=True)
class InterviewContext:
    """
    Runtime dependency bundle for one interview.
    """

    # ---------------------------------------------------------
    # Aggregate
    # ---------------------------------------------------------

    session: InterviewSession

    # ---------------------------------------------------------
    # Services
    # ---------------------------------------------------------

    evaluator: object

    question_generator: object

    knowledge_base: object

    memory: object

    metrics: object | None = None

    config: object | None = None

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def __post_init__(self) -> None:

        self.goal_manager = GoalManager(
            self.session.goal_states.values()
        )

    # ---------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------

    @property
    def current_goal_state(self):

        return self.goal_manager.current_goal_state

    @property
    def current_goal(self):

        return self.goal_manager.current_goal

    @property
    def interview_finished(self) -> bool:
        """Return navigation completion, not a possibly stale lifecycle flag.

        The session lifecycle is synchronized by AssessmentRuntime.  This
        compatibility context property must not let a stale ``session.completed``
        value short-circuit navigation while a non-terminal question exists.
        """

        return self.goal_manager.finished()

    def advance_goal(self):

        state = self.goal_manager.advance()

        self.session.current_goal_id = (
            state.goal.id
            if state
            else None
        )

        return state