"""
app/strategies/interviewer_strategy.py

Default interview-navigation strategy.

The strategy consumes the canonical GoalDecision contract produced
by the assessment layer.

It does not:
- evaluate answers
- calculate assessment metrics
- mutate assessment metrics
- directly manipulate indicator state
"""

from __future__ import annotations

from ..assessment.decision import (
    DecisionStatus,
    GoalDecision,
)
from ..interview.context import AssessmentContext


class InterviewerStrategy:
    """
    Coordinate goal/indicator navigation after assessment.
    """

    def next_indicator(
        self,
        context: AssessmentContext,
        decision: GoalDecision,
    ):
        """
        Determine the next indicator after an assessment decision.
        """

        if context is None:
            raise ValueError(
                "InterviewerStrategy requires an AssessmentContext."
            )

        if not isinstance(
            decision,
            GoalDecision,
        ):
            raise TypeError(
                "InterviewerStrategy requires a GoalDecision."
            )

        navigator = context.navigator

        # ------------------------------------------------------
        # Interview already finished
        # ------------------------------------------------------

        if context.is_finished:
            return None

        # ------------------------------------------------------
        # Terminal goal decision
        # ------------------------------------------------------
        #
        # COMPLETE and FAILED are both terminal for the current
        # goal. Goal advancement itself is navigation; academic
        # completion remains owned by the assessment layer.
        # ------------------------------------------------------

        if (
            decision.status
            in DecisionStatus.terminal_statuses()
        ):

            navigator.advance_goal(
                context
            )

            if navigator.finished(
                context
            ):
                return None

            return navigator.next_indicator(
                context
            )

        # ------------------------------------------------------
        # ProgressReasoner selected a specific indicator
        # ------------------------------------------------------
        #
        # Do not mutate GoalState directly.
        #
        # InterviewNavigator owns indicator activation and keeps
        # GoalState + AssessmentContext synchronized.
        # ------------------------------------------------------

        if decision.next_indicator is not None:

            return navigator.next_indicator(
                context,
                preferred=[
                    decision.next_indicator
                ],
            )

        # ------------------------------------------------------
        # No preferred indicator
        # ------------------------------------------------------

        return navigator.next_indicator(
            context
        )