"""
app/navigation/adaptive_navigation.py

Default adaptive navigation policy.

The policy is intentionally thin:

    EvidencePlanner
        owns indicator selection

    ProgressReasoner
        owns assessment progression decisions

AdaptiveNavigationPolicy only adapts those services to the
NavigationPolicy contract.
"""

from __future__ import annotations

from typing import Any

from ..assessment.decision import (
    DecisionStatus,
    GoalDecision,
)
from .navigation_policy import NavigationPolicy


class AdaptiveNavigationPolicy(NavigationPolicy):
    """
    Adapter between the navigation layer and assessment services.
    """

    def __init__(
        self,
        evidence_planner: Any,
        progress_reasoner: Any,
    ) -> None:

        if evidence_planner is None:
            raise ValueError(
                "AdaptiveNavigationPolicy requires an evidence_planner."
            )

        if progress_reasoner is None:
            raise ValueError(
                "AdaptiveNavigationPolicy requires a progress_reasoner."
            )

        self.evidence_planner = evidence_planner
        self.progress_reasoner = progress_reasoner

    # ==========================================================
    # Indicator Selection
    # ==========================================================

    def next_indicator(
        self,
        goal_state: Any,
    ) -> Any | None:

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

        return selector(
            goal_state
        )

    # ==========================================================
    # Progress Evaluation
    # ==========================================================

    def evaluate_progress(
        self,
        goal_state: Any,
    ) -> GoalDecision:
        """
        Delegate to the canonical ProgressReasoner API.

        ProgressReasoner exposes evaluate().

        The old implementation called decide(), which was an obsolete
        navigation contract.
        """

        evaluator = getattr(
            self.progress_reasoner,
            "evaluate",
            None,
        )

        if not callable(evaluator):
            raise AttributeError(
                "ProgressReasoner must provide 'evaluate()'."
            )

        decision = evaluator(
            goal_state
        )

        if not isinstance(
            decision,
            GoalDecision,
        ):
            raise TypeError(
                "ProgressReasoner.evaluate() must return GoalDecision."
            )

        return decision

    # ==========================================================
    # Goal Advancement
    # ==========================================================

    def should_advance(
        self,
        decision: GoalDecision,
    ) -> bool:

        if not isinstance(
            decision,
            GoalDecision,
        ):
            raise TypeError(
                "AdaptiveNavigationPolicy requires a GoalDecision."
            )

        return (
            decision.status
            in DecisionStatus.terminal_statuses()
        )

    # ==========================================================
    # Interview Completion
    # ==========================================================

    def is_finished(
        self,
        goal_manager: Any,
    ) -> bool:

        if goal_manager is None:
            raise ValueError(
                "AdaptiveNavigationPolicy requires a goal_manager."
            )

        finished = getattr(
            goal_manager,
            "finished",
            None,
        )

        if not callable(finished):
            raise AttributeError(
                "GoalManager must provide 'finished()'."
            )

        return bool(
            finished()
        )