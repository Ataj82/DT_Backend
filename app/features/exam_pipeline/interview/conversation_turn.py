"""
app/interview/conversation_turn.py

Represents one exchange during an assessment interview.

ConversationTurn is the runtime representation of a single
interviewer question and the learner's response.

Responsibilities
----------------
- Store the interviewer question.
- Store the learner answer.
- Store goal/indicator identity.
- Store conversational feedback.
- Store the assessment decision produced for the answer.
- Track whether this turn terminates the interview.
- Provide safe serialization for persistence/API layers.

Non-responsibilities
--------------------
- Assessment algorithms.
- Goal mastery calculations.
- Indicator scoring.
- Goal navigation.
- Question generation.
- Interview completion decisions.

Important distinction
---------------------
`completed` belongs to the conversation turn.

It means:

    "This turn represents the end of the interview."

It does NOT mean:

    "The learner mastered the current goal."

Goal mastery is owned by GoalState / AssessmentEngine.

The assessment decision is intentionally retained as a runtime object,
but is not serialized directly by `as_dict()` because assessment
decision objects may not be JSON serializable and belong to the
assessment layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ConversationTurn:
    """
    One interviewer/learner interaction.

    A normal turn contains:

        interviewer question
        learner answer
        goal
        indicator
        assessment decision

    A terminal turn contains:

        completed=True

    The terminal turn may either be the final unanswered completion
    message ("Interview complete.") or the previous answered turn
    marked as completed.
    """

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    index: int

    goal_id: str | None = None

    indicator_id: str | None = None

    # ---------------------------------------------------------
    # Conversation content
    # ---------------------------------------------------------

    question: str = ""

    answer: str = ""

    feedback: str | None = None

    # ---------------------------------------------------------
    # Timing
    # ---------------------------------------------------------

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ---------------------------------------------------------
    # Runtime assessment state
    # ---------------------------------------------------------
    #
    # These objects are deliberately kept separate from the
    # persisted conversation representation.
    #
    # ConversationService writes:
    #
    #     turn.decision = assessment_decision
    #
    # AssessmentEngine owns the meaning of that decision.
    #

    decision: Any = None

    # ---------------------------------------------------------
    # Conversation lifecycle
    # ---------------------------------------------------------

    completed: bool = False

    # ---------------------------------------------------------
    # Extensible metadata
    # ---------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =========================================================
    # Properties
    # =========================================================

    @property
    def answered(self) -> bool:
        """
        Return True when the learner provided a non-empty answer.
        """

        return bool(
            self.answer
            and self.answer.strip()
        )

    @property
    def has_question(self) -> bool:
        """
        Return True when the turn contains a non-empty question.
        """

        return bool(
            self.question
            and self.question.strip()
        )

    @property
    def is_terminal(self) -> bool:
        """
        Return whether this turn terminates the interview.

        This is intentionally equivalent to `completed`.

        It does not describe goal mastery.
        """

        return self.completed

    @property
    def has_decision(self) -> bool:
        """
        Return whether AssessmentEngine produced a decision.
        """

        return self.decision is not None

    @property
    def has_feedback(self) -> bool:
        """
        Return whether feedback is available for this turn.
        """

        return bool(
            self.feedback
            and self.feedback.strip()
        )

    # =========================================================
    # Mutation helpers
    # =========================================================

    def record_answer(
        self,
        answer: str,
    ) -> None:
        """
        Record the learner's answer.

        Empty answers are rejected because ConversationService
        already treats an empty answer as invalid input.
        """

        normalized = (answer or "").strip()

        if not normalized:
            raise ValueError(
                "Conversation turn answer cannot be empty."
            )

        self.answer = normalized

    def record_feedback(
        self,
        feedback: str | None,
    ) -> None:
        """
        Record interviewer/assessment feedback.

        Empty feedback is normalized to None.
        """

        if feedback is None:
            self.feedback = None
            return

        normalized = str(feedback).strip()

        self.feedback = (
            normalized
            if normalized
            else None
        )

    def record_decision(
        self,
        decision: Any,
    ) -> None:
        """
        Attach an assessment decision to this turn.

        The decision itself is intentionally opaque to this class.
        AssessmentEngine and ConversationService interpret it.
        """

        self.decision = decision

    def mark_completed(self) -> None:
        """
        Mark this conversation turn as the terminal interview turn.

        This does not modify goal mastery.
        """

        self.completed = True

    def add_metadata(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Add or replace one metadata value.
        """

        if not key or not key.strip():
            raise ValueError(
                "Conversation turn metadata key cannot be empty."
            )

        self.metadata[key] = value

    # =========================================================
    # Serialization
    # =========================================================

    def as_dict(self) -> dict[str, Any]:
        """
        Return the persistence/API representation of the turn.

        The raw `decision` object is intentionally excluded.

        Reasons:

        - it may not be JSON serializable;
        - it belongs to the assessment layer;
        - exposing it couples persistence to AssessmentEngine;
        - the public conversation representation should contain
          conversational state, not internal assessment objects.
        """

        return {
            "index": self.index,
            "goal_id": self.goal_id,
            "indicator_id": self.indicator_id,
            "question": self.question,
            "answer": self.answer,
            "feedback": self.feedback,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
            "completed": self.completed,
        }

    # =========================================================
    # Debugging
    # =========================================================

    def __repr__(self) -> str:
        """
        Provide a useful representation without dumping the full
        assessment decision object.
        """

        return (
            "ConversationTurn("
            f"index={self.index!r}, "
            f"goal_id={self.goal_id!r}, "
            f"indicator_id={self.indicator_id!r}, "
            f"question={self.question!r}, "
            f"answered={self.answered!r}, "
            f"has_decision={self.has_decision!r}, "
            f"completed={self.completed!r}"
            ")"
        )