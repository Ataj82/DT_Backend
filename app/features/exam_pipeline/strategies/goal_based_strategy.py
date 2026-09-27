"""
strategies/goal_based_strategy.py

Concrete implementation of a Goal-Based Adaptive Interviewer.

This strategy implements the adaptive interviewing policy using:

• GoalManager
• EvidencePlanner
• AssessmentEngine
• ProgressReasoner
• CoverageEngine
• QuestionGenerator

The strategy contains NO LLM prompting logic and NO assessment
algorithms. It orchestrates existing components.
"""

from __future__ import annotations

from typing import Any

from ..strategies.interviewer_strategy import InterviewerStrategy
from ..assessment.goal_manager import GoalDecision


class GoalBasedStrategy(InterviewerStrategy):
    """
    Goal-based adaptive interviewing strategy.
    """

    # =====================================================
    # Helpers
    # =====================================================

    @property
    def goal_manager(self):
        return self.components.goal_manager

    @property
    def evidence_planner(self):
        return self.components.evidence_planner

    @property
    def question_generator(self):
        return self.components.question_generator

    @property
    def assessment_engine(self):
        return self.components.assessment_engine

    @property
    def progress_reasoner(self):
        return self.components.progress_reasoner

    @property
    def coverage_engine(self):
        return self.components.coverage_engine

    # =====================================================
    # Lifecycle
    # =====================================================

    def initialize(
        self,
        session,
    ) -> None:
        """
        Initialize interview state.

        Reserved for future extensions.
        """
        return

    # =====================================================
    # Current Goal
    # =====================================================

    def current_goal(
        self,
        session,
    ):

        return self.goal_manager.current_goal

    # =====================================================

    def current_goal_state(
        self,
        session,
    ):

        goal = self.current_goal(session)

        if goal is None:
            return None

        return session.get_goal_state(goal.id)

    # =====================================================
    # Current Indicator
    # =====================================================

    def current_indicator(
        self,
        session,
    ):

        state = self.current_goal_state(session)

        if state is None:
            return None

        return state.current_indicator_id

    # =====================================================
    # Question Generation
    # =====================================================

    def next_question(
        self,
        session,
    ) -> str:

        state = self.current_goal_state(session)

        if state is None:
            raise RuntimeError(
                "Interview has completed."
            )

        indicator_id = (
            self.evidence_planner.select_next_indicator(
                state
            )
        )

        if indicator_id is None:

            self.goal_manager.advance_goal()

            if self.goal_manager.finished():

                raise RuntimeError(
                    "Interview has completed."
                )

            return self.next_question(session)

        question = (
            self.question_generator.generate(
                goal_state=state,
                indicator_id=indicator_id,
            )
        )

        session.add_question(

            question=question,

            goal_id=state.goal.id,

            indicator_id=indicator_id,

        )

        return question

    # =====================================================
    # Answer Processing
    # =====================================================

    def submit_answer(
        self,
        session,
        answer: str,
    ) -> GoalDecision:

        state = self.current_goal_state(session)

        session.add_answer(answer)

        self.assessment_engine.evaluate(

            goal_state=state,

            answer=answer,

        )

        decision = (
            self.progress_reasoner.decide(
                state
            )
        )

        if decision.status == "COMPLETE":

            self.goal_manager.advance_goal()

        return decision

    # =====================================================
    # Navigation
    # =====================================================

    def skip_goal(
        self,
        session,
    ) -> None:

        self.goal_manager.advance_goal()

    # =====================================================
    # Completion
    # =====================================================

    def is_finished(
        self,
        session,
    ) -> bool:

        return self.goal_manager.finished()

    # =====================================================
    # Report
    # =====================================================

    def report(
        self,
        session,
    ) -> dict[str, Any]:

        goals = []

        for goal_id, state in session.goal_states.items():

            goals.append(

                {

                    "goal_id": goal_id,

                    "goal_title": state.goal.title,

                    "coverage": self.coverage_engine.coverage(
                        state
                    ),

                    "mastery": state.mastery(),

                    "confidence": state.confidence(),

                    "completed": state.completed,

                }

            )

        return {

            "session_id": session.id,

            "student_id": session.student_id,

            "completed": self.is_finished(session),

            "goals": goals,

        }