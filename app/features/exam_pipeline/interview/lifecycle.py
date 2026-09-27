"""Single-source interview lifecycle invariants.

Goal/assessment outcomes are intentionally separate from interview lifecycle.
A goal may be failed/exhausted while the interview continues with another goal.
The only conversation-level terminal signal is a terminal ConversationTurn.
"""

from __future__ import annotations


class InterviewLifecycle:
    """Centralize lifecycle reconciliation and API protocol validation."""

    @staticmethod
    def synchronize_session(session, turn) -> bool:
        """Make the persisted session agree with the returned conversation turn.

        Returns the resulting interview-completed state.
        """
        if session is None or turn is None:
            raise ValueError("Lifecycle synchronization requires session and turn.")

        if bool(getattr(turn, "completed", False)):
            mark_completed = getattr(session, "mark_completed", None)
            if callable(mark_completed):
                mark_completed()
            else:
                session.completed = True
        else:
            mark_active = getattr(session, "mark_active", None)
            if callable(mark_active):
                mark_active()
            else:
                session.completed = False
                if hasattr(session, "finished_at"):
                    session.finished_at = None

        return bool(getattr(session, "completed", False))


    @staticmethod
    def assert_session_turn_consistency(*, session, turn) -> None:
        """Reject an impossible persisted lifecycle state.

        A non-terminal returned question means the interview is active.
        A terminal returned turn is the only turn-level signal that permits
        interview completion.
        """
        if session is None or turn is None:
            raise ValueError("Lifecycle consistency requires session and turn.")

        turn_completed = bool(getattr(turn, "completed", False))
        session_completed = bool(getattr(session, "completed", False))

        if not turn_completed and session_completed:
            raise RuntimeError(
                "Interview lifecycle violation: non-terminal turn cannot "
                "coexist with session.completed=True."
            )

        if turn_completed and not session_completed:
            raise RuntimeError(
                "Interview lifecycle violation: terminal turn requires "
                "session.completed=True."
            )

    @staticmethod
    def response_state(next_question) -> tuple[bool, str]:
        """Derive API lifecycle strictly from next-question presence."""
        completed = next_question is None
        return completed, "completed" if completed else "running"

    @staticmethod
    def assert_response_invariant(*, next_question, interview_completed: bool) -> None:
        """Reject contradictory API lifecycle states."""
        expected = next_question is None
        if bool(interview_completed) != expected:
            raise RuntimeError(
                "Interview lifecycle protocol violation: "
                "next_question presence and interview_completed disagree."
            )
