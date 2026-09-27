from types import SimpleNamespace

from app.conversation.service import ConversationService


def _service():
    return ConversationService.__new__(ConversationService)


def _context(evidence):
    goal_state = SimpleNamespace(evidence=[evidence])
    navigator = SimpleNamespace(current_goal_state=lambda context: goal_state)
    return SimpleNamespace(navigator=navigator, session=SimpleNamespace())


def test_strong_evidence_promotes_bloom_one_level():
    evidence = SimpleNamespace(
        indicator_id="i1",
        achievement_level=6,
        confidence=0.9,
        evidence_strength=0.9,
        indicator_demonstrated=True,
    )
    context = _context(evidence)
    service = _service()
    goal = SimpleNamespace(bloom_level="apply")
    assert service._question_bloom_level(
        context=context, goal=goal, goal_state=None, indicator_id="i1"
    ) == "analyze"


def test_weak_evidence_does_not_drop_below_goal_bloom():
    evidence = SimpleNamespace(
        indicator_id="i1",
        achievement_level=2,
        confidence=0.9,
        evidence_strength=0.9,
        indicator_demonstrated=False,
    )
    context = _context(evidence)
    service = _service()
    goal = SimpleNamespace(bloom_level="apply")
    assert service._question_bloom_level(
        context=context, goal=goal, goal_state=None, indicator_id="i1"
    ) == "apply"


def test_highest_bloom_does_not_overflow():
    evidence = SimpleNamespace(
        indicator_id="i1",
        achievement_level=6,
        confidence=0.95,
        evidence_strength=0.95,
        indicator_demonstrated=True,
    )
    context = _context(evidence)
    service = _service()
    goal = SimpleNamespace(bloom_level="create")
    assert service._question_bloom_level(
        context=context, goal=goal, goal_state=None, indicator_id="i1"
    ) == "create"
