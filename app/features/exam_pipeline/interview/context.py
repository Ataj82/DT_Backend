"""
app/interview/context.py

Runtime assessment context.

The AssessmentContext stores all mutable runtime state used during
an interview session. It acts as the shared execution context for
the AssessmentRuntime and its collaborators.

The context owns runtime state only. Orchestration, assessment
reasoning, navigation decisions, and question generation remain
delegated to their respective collaborators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AssessmentContext:
    """
    Shared runtime context for one interview session.

    This object is session-scoped. It is reconstructed from the
    persistent InterviewSession whenever an AssessmentRuntime is
    created.

    The context deliberately contains no interview orchestration
    logic. Its mutation helpers only update runtime bookkeeping.
    """

    # ==========================================================
    # Session
    # ==========================================================

    session: Any

    configuration: Any

    student_id: str

    knowledge_model: Any

    goal_model: Any

    # ==========================================================
    # Runtime Components
    # ==========================================================

    goal_manager: Any

    navigator: Any

    strategy: Any

    coverage_engine: Any

    evidence_planner: Any

    progress_reasoner: Any

    question_generator: Any

    result_builder: Any

    # Optional ABET application service; absent means legacy v7.x mode.
    abet_service: Any | None = None

    # Optional runtime collaborators retained for compatibility
    # with existing composition and future runtime extensions.
    information_gain_planner: Any | None = None

    time_manager: Any | None = None

    # ==========================================================
    # Runtime State
    # ==========================================================

    current_goal_id: str | None = None

    current_indicator_id: str | None = None

    interview_completed: bool = False

    current_question: str | None = None

    last_answer: str | None = None

    # ==========================================================
    # Assessment State
    # ==========================================================

    assessment_state: dict[str, Any] = field(
        default_factory=dict
    )

    conversation_history: list[Any] = field(
        default_factory=list
    )

    evidence: list[Any] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ==========================================================
    # Runtime Statistics
    # ==========================================================

    questions_asked: int = 0

    answers_received: int = 0

    completed_goals: int = 0

    # ==========================================================
    # Compatibility / State Access
    # ==========================================================

    @property
    def state(self) -> dict[str, Any]:
        """
        Backward-compatible alias for assessment_state.

        Existing assessment components may use ``context.state``.
        Keeping this alias avoids breaking those callers.
        """

        return self.assessment_state

    @property
    def current_goal(self):
        """
        Return the currently active goal.

        Goal navigation remains owned by GoalManager.
        """

        if self.goal_manager is None:
            return None

        return self.goal_manager.current_goal

    @property
    def current_goal_state(self):
        """
        Return the mutable runtime state for the current goal.

        The session's public ``get_goal_state`` API is preferred when
        available. The ``goal_states`` mapping remains supported for
        compatibility with existing InterviewSession implementations.
        """

        goal = self.current_goal

        if goal is None:
            return None

        # Preferred session API.
        get_goal_state = getattr(
            self.session,
            "get_goal_state",
            None,
        )

        if callable(get_goal_state):
            return get_goal_state(goal.id)

        # Backward-compatible direct mapping access.
        goal_states = getattr(
            self.session,
            "goal_states",
            None,
        )

        if goal_states is None:
            return None

        return goal_states.get(goal.id)

    @property
    def interview_template(self):
        """
        Return the configured interview template.

        The configuration object is intentionally kept opaque here;
        configuration-specific behavior belongs to the configuration
        layer.
        """

        if self.configuration is None:
            return None

        return getattr(
            self.configuration,
            "interview_template",
            None,
        )

    @property
    def current_indicator(self):
        """
        Return the currently active indicator.

        Indicator selection remains the responsibility of the
        InterviewNavigator.
        """

        if self.navigator is None:
            return None

        if self.current_goal is None:
            return None

        return self.navigator.current_indicator(self)

    # ==========================================================
    # Runtime Bookkeeping
    # ==========================================================

    def add_question(
        self,
        question: str,
    ) -> None:
        """
        Record a generated interviewer question.
        """

        self.current_question = question

        self.questions_asked += 1

        self.conversation_history.append(
            {
                "role": "assistant",
                "content": question,
            }
        )

    def add_answer(
        self,
        answer: str,
    ) -> None:
        """
        Record a learner answer.
        """

        self.last_answer = answer

        self.answers_received += 1

        self.conversation_history.append(
            {
                "role": "user",
                "content": answer,
            }
        )

    def add_evidence(
        self,
        evidence: Any,
    ) -> None:
        """
        Add evidence collected during the interview.

        Assessment and validation of evidence remain outside the
        context.
        """

        self.evidence.append(evidence)

    def increment_completed_goals(self) -> None:
        """
        Increment the number of completed goals.
        """

        self.completed_goals += 1

    # ==========================================================
    # Completion
    # ==========================================================

    def mark_completed(self) -> None:
        """
        Mark the interview as completed.
        """

        self.interview_completed = True

    # ==========================================================
    # Runtime Reset Helpers
    # ==========================================================

    def reset_current_indicator(self) -> None:
        """
        Clear the active indicator.
        """

        self.current_indicator_id = None

    def reset_current_question(self) -> None:
        """
        Clear the currently active question.
        """

        self.current_question = None

    # ==========================================================
    # Status
    # ==========================================================

    @property
    def is_finished(self) -> bool:
        """
        Return whether the interview has completed.
        """

        return self.interview_completed