"""
serialization/context_serializer.py

Serializes AssessmentContext.

This serializer intentionally stores only runtime state.
Runtime services are reconstructed by AssessmentRuntimeFactory.
"""

from __future__ import annotations

from datetime import datetime

from ..interview.context import AssessmentContext
from ..conversation.history import ConversationHistory
from ..serialization.serializer import Serializer


class AssessmentContextSerializer(Serializer):

    # ---------------------------------------------------------
    # Serialize
    # ---------------------------------------------------------

    def serialize(
        self,
        context: AssessmentContext,
    ) -> dict:

        return {

            "session_id": context.session.id,

            "student_id": context.student_id,

            "configuration": context.configuration,

            "knowledge_model": context.knowledge_model,

            "goal_model": context.goal_model,

            "current_goal_id": context.current_goal_id,

            "current_indicator_id": context.current_indicator_id,

            "questions_asked": context.questions_asked,

            "answers_received": context.answers_received,

            "interview_completed":
                context.interview_completed,

            "started_at":
                context.started_at.isoformat(),

            "completed_at": (
                context.completed_at.isoformat()
                if context.completed_at
                else None
            ),

            "metadata": context.metadata,

            "history": [

                {

                    "number": turn.number,

                    "question": turn.question,

                    "answer": turn.answer,

                    "goal_id": turn.goal_id,

                    "indicator_id": turn.indicator_id,

                    "completed": turn.completed,

                }

                for turn
                in context.history.turns
            ]
        }

    # ---------------------------------------------------------
    # Deserialize
    # ---------------------------------------------------------

    def deserialize(
        self,
        data: dict,
    ) -> dict:
        """
        Returns runtime state.

        AssessmentRuntimeFactory is responsible for
        reconstructing AssessmentContext using these values.
        """

        history = ConversationHistory()

        for item in data.get(
            "history",
            [],
        ):

            history.turns.append(
                self._deserialize_turn(item)
            )

        return {

            "session_id":
                data["session_id"],

            "student_id":
                data["student_id"],

            "configuration":
                data["configuration"],

            "knowledge_model":
                data["knowledge_model"],

            "goal_model":
                data["goal_model"],

            "current_goal_id":
                data["current_goal_id"],

            "current_indicator_id":
                data["current_indicator_id"],

            "questions_asked":
                data["questions_asked"],

            "answers_received":
                data["answers_received"],

            "interview_completed":
                data["interview_completed"],

            "started_at":
                datetime.fromisoformat(
                    data["started_at"]
                ),

            "completed_at": (
                datetime.fromisoformat(
                    data["completed_at"]
                )
                if data["completed_at"]
                else None
            ),

            "metadata":
                data["metadata"],

            "history":
                history,
        }

    # ---------------------------------------------------------
    # Turn
    # ---------------------------------------------------------

    def _deserialize_turn(
        self,
        item: dict,
    ):

        from ..conversation.models import (
            ConversationTurn,
        )

        return ConversationTurn(

            number=item["number"],

            question=item["question"],

            answer=item.get("answer"),

            goal_id=item.get("goal_id"),

            indicator_id=item.get(
                "indicator_id"
            ),

            completed=item.get(
                "completed",
                False,
            ),
        )