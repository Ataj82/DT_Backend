from types import SimpleNamespace

from app.assessment.evidence_planner import EvidencePlanner


class DummyIG:
    def utility(self, goal_state, indicator):
        return 1.0



def planner():
    return EvidencePlanner(information_gain_planner=DummyIG())


def test_unassessed_indicator_is_eligible():
    indicator = SimpleNamespace(
        id="i1", achievement_level=None, confidence=None, evidence_strength=None
    )
    assert planner().can_assess(indicator) is True


def test_sufficient_evidence_stops_regardless_of_attempts():
    p = planner()
    indicator = SimpleNamespace(
        id="i1", achievement_level=2, confidence=0.9, evidence_strength=0.9, attempts=1
    )
    assert p.can_assess(indicator) is False
    indicator.attempts = 99
    assert p.can_assess(indicator) is False


def test_low_mastery_with_strong_evidence_stops():
    indicator = SimpleNamespace(
        id="i1", achievement_level=1, confidence=0.95, evidence_strength=0.95, attempts=2
    )
    assert planner().can_assess(indicator) is False


def test_weak_evidence_remains_eligible_even_after_many_attempts():
    indicator = SimpleNamespace(
        id="i1", achievement_level=4, confidence=0.9, evidence_strength=0.2, attempts=99
    )
    assert planner().can_assess(indicator) is True


def test_remaining_attempts_is_compatibility_signal_not_budget():
    indicator = SimpleNamespace(
        id="i1", achievement_level=4, confidence=0.9, evidence_strength=0.2, attempts=999
    )
    assert planner().remaining_attempts(indicator) == 1
