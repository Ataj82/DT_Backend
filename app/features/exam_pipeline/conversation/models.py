"""
conversation/models.py

Conversation domain models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..assessment.decision import GoalDecision


@dataclass(slots=True)
class ConversationTurn:
    """
    Represents one interview turn.

    One turn consists of:
        Question
        Student answer
        Assessment
        Next question
    """

    number: int

    question: str

    answer: Optional[str] = None

    goal_id: Optional[str] = None

    indicator_id: Optional[str] = None

    decision: Optional[GoalDecision] = None

    next_question: Optional[str] = None

    completed: bool = False

    timestamp: datetime = field(default_factory=datetime.utcnow)