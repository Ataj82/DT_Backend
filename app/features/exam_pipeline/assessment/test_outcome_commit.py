from types import SimpleNamespace

from app.assessment.goal_state import GoalState, IndicatorState
from app.assessment.outcome_manager import OutcomeManager
from app.assessment.evaluation.answer_evaluator import AnswerEvidence


class _Coverage:
    def is_complete(self, goal_state):
        return False


class _Goal:
    def __init__(self):
        self.id = "goal-1"
        self.indicators = []


def _state():
    return GoalState(
        goal=_Goal(),
        indicators={
            "ind-1": IndicatorState(
                id="ind-1",
                description="test",
                bloom_level="apply",
            )
        },
    )


def _evidence():
    return AnswerEvidence(
        indicator_id="ind-1",
        achievement_level=4,
        confidence=0.8,
        evidence_strength=0.8,
        indicator_demonstrated=True,
        feedback="Correct.",
        turn_index=1,
        question="Q",
        answer="A",
    )


def test_goal_state_add_evidence_does_not_increment_attempts():
    state = _state()
    state.add_evidence(_evidence())
    assert state.indicators["ind-1"].attempts == 0
    assert state.indicators["ind-1"].demonstrated is False


def test_outcome_manager_apply_evaluation_increments_attempt_once():
    state = _state()
    manager = OutcomeManager(coverage_engine=_Coverage())

    manager.apply_evaluation(
        state,
        indicator_id="ind-1",
        evidence=_evidence(),
        turn_index=1,
    )

    assert state.indicators["ind-1"].attempts == 1
    assert len(state.evidence) == 1
