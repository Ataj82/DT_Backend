from types import SimpleNamespace

from app.interview.prompt_builder import QuestionPromptBuilder


def test_prompt_contains_target_difficulty_without_changing_bloom():
    request = SimpleNamespace(
        goal=SimpleNamespace(title="Python", description="Explain Python", bloom_level="apply"),
        indicator=SimpleNamespace(name="functions", description="Use functions"),
        interview_template=SimpleNamespace(
            metadata={"language": "English"},
            probe_policy=SimpleNamespace(value="adaptive"),
        ),
        previous_feedback="Missing edge cases.",
        question_focus="Use a different scenario.",
        difficulty=0.8,
        difficulty_reason="strong performance -> increase challenge",
    )
    prompt = QuestionPromptBuilder().build(request, "function context", "1. Old question")
    assert "Target Difficulty" in prompt
    assert "0.8" in prompt
    assert "strong performance" in prompt
    assert "Bloom Level" in prompt
