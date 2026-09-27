"""
conversation/history.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

#from .models import ConversationTurn
from ..interview.conversation_turn import ConversationTurn

@dataclass(slots=True)
class ConversationHistory:

    turns: list[ConversationTurn] = field(default_factory=list)

    def add(self, turn: ConversationTurn):

        self.turns.append(turn)

    @property
    def last(self):

        if not self.turns:
            return None

        return self.turns[-1]

    @property
    def turn_number(self):

        return len(self.turns) + 1

    def completed(self):

        return (
            self.last is not None
            and self.last.completed
        )