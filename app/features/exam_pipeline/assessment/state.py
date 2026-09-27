"""
app/assessment/state.py

Runtime state models for the assessment engine.

This module currently supports both:

1. Goal-based assessment state.
2. Legacy outcome-based assessment state.

The outcome API is intentionally preserved for compatibility with
existing assessment components. A later refactor can remove the
legacy outcome layer once all consumers have migrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .outcome_models import OutcomeState


# ==========================================================
# Skill State
# ==========================================================


@dataclass
class SkillState:
    """
    Runtime state for one skill.

    This model is retained for components that track skill-level
    evidence independently from goal-level state.
    """

    skill_id: str

    evidence: list = field(
        default_factory=list
    )

    attempts: int = 0

    mastery_score: float = 0.0


# ==========================================================
# Goal State
# ==========================================================


@dataclass
class GoalState:
    """
    Runtime state for one assessment goal.

    The fields intentionally preserve the existing contract:

        goal_id
        attempts
        scores
        completed
        failed

    Completion and failure are kept separate because an assessment
    can distinguish successful completion from an explicitly failed
    goal.
    """

    goal_id: str

    attempts: int = 0

    scores: List[float] = field(
        default_factory=list
    )

    completed: bool = False

    failed: bool = False


# ==========================================================
# Assessment State
# ==========================================================


@dataclass
class AssessmentState:
    """
    Complete runtime state of an assessment.

    The state currently contains both goal-based and outcome-based
    representations.

    Goal-based flow:

        goals
        ↓
        GoalState

    Legacy outcome flow:

        outcomes
        ↓
        OutcomeState

    Both are intentionally preserved until all consumers have been
    migrated to the canonical goal/indicator architecture.
    """

    # ------------------------------------------------------
    # Goal-Based Assessment
    # ------------------------------------------------------

    goals: Dict[str, GoalState] = field(
        default_factory=dict
    )

    # ------------------------------------------------------
    # Outcome-Based Assessment
    # ------------------------------------------------------

    outcomes: Dict[str, OutcomeState] = field(
        default_factory=dict
    )

    # ------------------------------------------------------
    # Runtime Counters
    # ------------------------------------------------------

    turn_count: int = 0

    interview_complete: bool = False

    # ======================================================
    # Outcome Registration
    # ======================================================

    def register_outcome(
        self,
        outcome_state: OutcomeState,
    ) -> None:
        """
        Register or replace an outcome state.

        Existing behavior is preserved: if the same outcome_id
        already exists, the new state replaces it.
        """

        self.outcomes[
            outcome_state.outcome_id
        ] = outcome_state

    # ======================================================
    # Outcome Retrieval
    # ======================================================

    def get_outcome(
        self,
        outcome_id: str,
    ) -> Optional[OutcomeState]:
        """
        Return an outcome by ID.

        Returns None when the outcome does not exist.
        """

        return self.outcomes.get(
            outcome_id
        )

    # ======================================================
    # Outcome Existence
    # ======================================================

    def has_outcome(
        self,
        outcome_id: str,
    ) -> bool:
        """
        Return True when an outcome is registered.
        """

        return outcome_id in self.outcomes

    # ======================================================
    # Outcome Removal
    # ======================================================

    def remove_outcome(
        self,
        outcome_id: str,
    ) -> None:
        """
        Remove an outcome if it exists.

        Missing outcomes are ignored, preserving the original
        behavior of dict.pop(..., None).
        """

        self.outcomes.pop(
            outcome_id,
            None,
        )

    # ======================================================
    # Outcome Count
    # ======================================================

    def outcome_count(
        self,
    ) -> int:
        """
        Return the number of registered outcomes.
        """

        return len(
            self.outcomes
        )

    # ======================================================
    # Registered Outcomes
    # ======================================================

    def registered_outcomes(
        self,
    ) -> List[str]:
        """
        Return the IDs of all registered outcomes.

        The order is the insertion order of the underlying dict,
        matching the existing implementation.
        """

        return list(
            self.outcomes.keys()
        )