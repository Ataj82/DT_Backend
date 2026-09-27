from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InterviewConfiguration:

    max_questions: int = 25

    # Deprecated compatibility field; attempts never control interview flow.
    max_attempts_per_indicator: int | None = None

    confidence_threshold: float = 0.75

    stop_when_all_goals_completed: bool = True

    allow_follow_up_questions: bool = True

    enable_adaptive_navigation: bool = True