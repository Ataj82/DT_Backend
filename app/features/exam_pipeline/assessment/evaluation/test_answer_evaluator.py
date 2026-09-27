from types import SimpleNamespace

import pytest

from ....app.assessment.evaluation.answer_evaluator import (
    AnswerEvaluationError,
    AnswerEvaluator,
)


class FakeEvaluatorLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if callable(response):
            return response(messages)
        return response


def make_goal():
    indicator = SimpleNamespace(
        id="indicator-1",
        name="python",
        description="Demonstrate understanding of Python.",
        bloom_level="understand",
    )
    return SimpleNamespace(
        name="Demonstrate understanding of python",
        description="Demonstrate understanding of Python.",
        indicators={"indicator-1": indicator},
    )


def response_from_prompt(*, achievement=4, feedback="Good explanation.", rationale="Relevant evidence.", demonstrated=True, confidence=0.9, evidence_strength=0.9):
    def _response(messages):
        prompt = messages[-1]["content"]
        fingerprint = next(
            line.split("REQUEST_FINGERPRINT_VALUE:", 1)[1].strip()
            for line in prompt.splitlines()
            if line.startswith("REQUEST_FINGERPRINT_VALUE:")
        )
        nonce = next(
            line.split("REQUEST_ATTEMPT_NONCE:", 1)[1].strip()
            for line in prompt.splitlines()
            if line.startswith("REQUEST_ATTEMPT_NONCE:")
        )
        lines = prompt.splitlines()
        answer_start = lines.index("LEARNER ANSWER") + 1
        answer = lines[answer_start].strip()
        return __import__("json").dumps({
            "achievement_level": achievement,
            "confidence": confidence,
            "evidence_strength": evidence_strength,
            "indicator_demonstrated": demonstrated,
            "feedback": feedback,
            "rationale": rationale,
            "missing_elements": [],
            "evidence_quotes": [answer] if demonstrated and answer else [],
            "request_fingerprint": fingerprint,
            "request_nonce": nonce,
        })
    return _response


def test_current_request_identity_is_required_and_preserved():
    llm = FakeEvaluatorLLM([
        response_from_prompt(
            feedback="The Python explanation is clear.",
            rationale="The answer identifies Python as a high-level language.",
        )
    ])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="What is Python?",
        answer="Python is a high-level programming language.",
        turn_index=7,
    )

    expected = evaluator._request_fingerprint(
        turn_index=7,
        question="What is Python?",
        answer="Python is a high-level programming language.",
    )

    assert evidence.turn_index == 7
    assert evidence.question == "What is Python?"
    assert evidence.answer == "Python is a high-level programming language."
    assert evidence.request_fingerprint == expected
    assert len(llm.calls) == 1


def test_stale_response_is_rejected_and_current_response_is_retried():
    stale_fingerprint = AnswerEvaluator._request_fingerprint(
        turn_index=5,
        question="What is a list comprehension?",
        answer="It creates a list from an iterable.",
    )

    def stale_response(_messages):
        return __import__("json").dumps({
            "achievement_level": 4,
            "confidence": 0.9,
            "evidence_strength": 0.9,
            "indicator_demonstrated": True,
            "feedback": "The function correctly filters students who scored above 80.",
            "rationale": "The answer builds a dictionary of score frequencies.",
            "missing_elements": [],
            "request_fingerprint": stale_fingerprint,
            "request_nonce": "stale",
        })

    llm = FakeEvaluatorLLM([
        stale_response,
        response_from_prompt(
            feedback="The Python explanation is relevant to the current question.",
            rationale="The answer directly explains Python as a high-level language.",
        ),
    ])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="What is Python?",
        answer="Python is a high-level programming language.",
        turn_index=6,
    )

    assert len(llm.calls) == 2
    assert evidence.feedback.startswith("The Python explanation")
    assert evidence.rationale.startswith("The answer directly explains")


def test_fabricated_evidence_quote_is_ignored_and_application_grounding_is_used():
    def fabricated(messages):
        prompt = messages[-1]["content"]
        fingerprint = next(
            line.split("REQUEST_FINGERPRINT_VALUE:", 1)[1].strip()
            for line in prompt.splitlines()
            if line.startswith("REQUEST_FINGERPRINT_VALUE:")
        )
        nonce = next(
            line.split("REQUEST_ATTEMPT_NONCE:", 1)[1].strip()
            for line in prompt.splitlines()
            if line.startswith("REQUEST_ATTEMPT_NONCE:")
        )
        return __import__("json").dumps({
            "achievement_level": 5,
            "confidence": 0.95,
            "evidence_strength": 0.95,
            "indicator_demonstrated": True,
            "feedback": "Strong answer.",
            "rationale": "The learner correctly explains the concept.",
            "missing_elements": [],
            "evidence_quotes": ["This claim was never said by the learner."],
            "request_fingerprint": fingerprint,
            "request_nonce": nonce,
        })

    llm = FakeEvaluatorLLM([fabricated])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="What is Python?",
        answer="Python is a high-level programming language.",
        turn_index=2,
    )

    assert len(llm.calls) == 1
    assert evidence.evidence_quotes == [
        "Python is a high-level programming language."
    ]


def test_explicit_refusal_cannot_receive_positive_demonstration():
    llm = FakeEvaluatorLLM([
        response_from_prompt(achievement=6, demonstrated=True, evidence_strength=1.0)
    ])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="What is Python?",
        answer="I don't know.",
        turn_index=8,
    )

    assert evidence.achievement_level == 2
    assert evidence.indicator_demonstrated is False
    assert evidence.evidence_strength == 0.10
    assert evidence.evidence_quotes == ["I don't know."]
    assert "does not provide evidence" in evidence.feedback.lower()


def test_missing_fingerprint_fails_closed_after_retries():
    response = __import__("json").dumps({
        "achievement_level": 4,
        "confidence": 0.9,
        "evidence_strength": 0.9,
        "indicator_demonstrated": True,
        "feedback": "Good explanation.",
        "rationale": "Relevant evidence.",
        "missing_elements": [],
    })

    llm = FakeEvaluatorLLM([response, response, response])
    evaluator = AnswerEvaluator(llm=llm)

    with pytest.raises(AnswerEvaluationError, match="Answer evaluation failed after 3 attempts"):
        evaluator.evaluate(
            goal=make_goal(),
            indicator_id="indicator-1",
            question="What is Python?",
            answer="Python is a programming language.",
            turn_index=1,
        )

    assert len(llm.calls) == evaluator.MAX_IDENTITY_RETRIES + 1


def test_malformed_json_is_repaired_on_retry():
    llm = FakeEvaluatorLLM([
        "{\"achievement_level\": 4,",
        response_from_prompt(),
    ])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="What is Python?",
        answer="Python is a high-level programming language.",
        turn_index=3,
    )

    assert len(llm.calls) == 2
    retry_prompt = llm.calls[1][-1]["content"]
    assert "RETRY REQUIREMENT" in retry_prompt
    assert "ONLY one valid JSON object" in retry_prompt
    assert evidence.achievement_level == 4


def test_long_answer_is_preserved_for_evaluation():
    answer = "Python list comprehensions are concise. " * 1000
    llm = FakeEvaluatorLLM([response_from_prompt(demonstrated=False, achievement=2)])
    evaluator = AnswerEvaluator(llm=llm)

    evidence = evaluator.evaluate(
        goal=make_goal(),
        indicator_id="indicator-1",
        question="Explain Python.",
        answer=answer,
        turn_index=4,
    )

    prompt = llm.calls[0][-1]["content"]
    assert answer.strip() in prompt
    assert evidence.answer == answer.strip()
