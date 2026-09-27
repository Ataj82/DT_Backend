"""
app/navigation/navigation_policy.py

Canonical navigation-policy contract.

A navigation policy decides how an already-evaluated assessment
result should influence interview navigation. It does not evaluate
answers, mutate assessment state, or persist sessions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..assessment.decision import GoalDecision


class NavigationPolicy(ABC):
    """
    Interface implemented by interview navigation policies.
    """

    @abstractmethod
    def next_indicator(
        self,
        goal_state: Any,
    ) -> Any | None:
        """
        Return the next assessable indicator, or None.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate_progress(
        self,
        goal_state: Any,
    ) -> GoalDecision:
        """
        Evaluate committed assessment state and return a decision.
        """
        raise NotImplementedError

    @abstractmethod
    def should_advance(
        self,
        decision: GoalDecision,
    ) -> bool:
        """
        Return True when the current goal should be advanced.
        """
        raise NotImplementedError

    @abstractmethod
    def is_finished(
        self,
        goal_manager: Any,
    ) -> bool:
        """
        Return True when no goals remain.
        """
        raise NotImplementedError