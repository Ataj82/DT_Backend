"""Immutable identity of one learner-answer evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Immutable snapshot of the turn being evaluated."""

    turn_index: int
    goal_id: str
    indicator_id: str
    question: str
    answer: str

    def __post_init__(self) -> None:
        if not isinstance(self.turn_index, int) or self.turn_index < 1:
            raise ValueError("EvaluationContext.turn_index must be a positive integer.")
        for name in ("goal_id", "indicator_id", "question", "answer"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"EvaluationContext.{name} must be a non-empty string.")

        object.__setattr__(self, "goal_id", self.goal_id.strip())
        object.__setattr__(self, "indicator_id", self.indicator_id.strip())
        object.__setattr__(self, "question", self.question.strip())
        object.__setattr__(self, "answer", self.answer.strip())
