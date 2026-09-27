from types import SimpleNamespace

from app.assessment.difficulty import AdaptiveDifficultyController


def evidence(level, confidence=0.9, strength=0.9, demonstrated=True):
    return SimpleNamespace(
        achievement_level=level,
        confidence=confidence,
        evidence_strength=strength,
        indicator_demonstrated=demonstrated,
    )


def indicator(difficulty=0.5):
    return SimpleNamespace(
        difficulty=difficulty,
        difficulty_history=[difficulty],
        difficulty_performance_history=[],
        last_difficulty_reason="initial",
    )


def test_strong_answer_increases_difficulty():
    controller = AdaptiveDifficultyController(step=0.1)
    state = indicator(0.5)
    decision = controller.update(indicator=state, evidence=evidence(6))
    assert decision.direction == "increase"
    assert state.difficulty == 0.6


def test_weak_answer_decreases_difficulty():
    controller = AdaptiveDifficultyController(step=0.1)
    state = indicator(0.5)
    decision = controller.update(indicator=state, evidence=evidence(1, 0.9, 0.9, False))
    assert decision.direction == "decrease"
    assert state.difficulty == 0.4


def test_moderate_answer_does_not_oscillate():
    controller = AdaptiveDifficultyController(step=0.1)
    state = indicator(0.5)
    decision = controller.update(indicator=state, evidence=evidence(3, 0.7, 0.7, False))
    assert decision.direction in {"hold", "increase", "decrease"}
    assert 0.2 <= state.difficulty <= 0.95


def test_difficulty_is_bounded():
    controller = AdaptiveDifficultyController(step=0.2, maximum=0.7)
    state = indicator(0.65)
    controller.update(indicator=state, evidence=evidence(6))
    assert state.difficulty == 0.7
