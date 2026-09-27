from app.assessment.evaluation.answer_evaluator import AnswerEvaluator


def test_evidence_quotes_are_owned_by_application_not_llm():
    answer = "I use a dictionary to count each string.\n\nFor case sensitivity, I keep the original string as the key."
    quotes = AnswerEvaluator._extract_evidence_quotes(
        answer=answer,
        question="Explain dictionary counting and case sensitivity.",
        indicator=type("Indicator", (), {
            "name": "dictionary counting",
            "description": "Count strings and preserve case.",
        })(),
        rationale="The learner explains counting and preserves case.",
        feedback="Good explanation.",
    )
    assert quotes
    assert all(q in answer for q in quotes)
    assert sum(map(len, quotes)) <= 1500


def test_llm_fabricated_evidence_is_not_authoritative():
    answer = "I use a dictionary to count each string."
    quotes = AnswerEvaluator._evidence_quotes(
        {"evidence_quotes": ["fabricated paraphrase not in answer"]},
        answer=answer,
        achievement_level=5,
        indicator_demonstrated=True,
    )
    assert quotes == [answer]
