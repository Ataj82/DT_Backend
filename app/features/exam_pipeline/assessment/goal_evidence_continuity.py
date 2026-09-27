"""Evidence continuity guard for adaptive interview question generation.

v12.2

The adaptive stack may correctly select an indicator while an LLM still
produces a question about a neighboring topic.  This manager adds a small,
deterministic boundary around question generation:

    selected indicator -> evidence focus -> generated question

It does not select goals, score answers, change difficulty, or replace the
existing EvidencePlanner.  It only rejects generated questions that have no
meaningful lexical connection to the evidence target and gives the generator
a stronger correction prompt before retrying.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


class QuestionContinuityError(RuntimeError):
    """Raised when generation repeatedly leaves the active evidence target."""


class GoalEvidenceContinuityManager:
    VERSION = "12.2"
    METADATA_KEY = "goal_evidence_continuity"
    MAX_RETRIES = 3
    MIN_ANCHOR_MATCHES = 1
    MIN_TOKEN_LENGTH = 4

    _TOKEN_RE = re.compile(r"[a-z][a-z0-9_+-]{2,}")
    _STOPWORDS = {
        "about", "after", "again", "also", "answer", "answers", "asking",
        "because", "being", "between", "could", "does", "doing", "during",
        "each", "explain", "example", "examples", "from", "given", "give",
        "given", "goal", "how", "into", "more", "most", "only", "question",
        "should", "that", "their", "them", "then", "this", "through", "using",
        "what", "when", "where", "which", "while", "with", "would", "your",
        "you", "describe", "provide", "show", "write", "code", "function",
        "program", "programming", "implementation", "implement", "solution",
        "approach", "method", "way", "correct", "work", "works", "working",
        "used", "use", "uses", "make", "makes", "made", "data", "item", "items",
        "input", "output", "value", "values", "result", "results", "case", "cases",
        "specific", "concept", "concepts", "understanding", "understand", "knowledge", "indicator",
    }

    def __init__(self, session: Any):
        if session is None:
            raise ValueError("GoalEvidenceContinuityManager requires a session.")
        self.session = session
        self._ensure_state()

    def _ensure_state(self) -> None:
        metadata = getattr(self.session, "metadata", None)
        if not isinstance(metadata, dict):
            raise TypeError("GoalEvidenceContinuityManager requires session.metadata to be a dict.")
        state = metadata.get(self.METADATA_KEY)
        if not isinstance(state, dict) or state.get("version") != self.VERSION:
            state = {
                "version": self.VERSION,
                "accepted": 0,
                "rejected": 0,
                "last": None,
            }
            metadata[self.METADATA_KEY] = state
        self.state = state

    @classmethod
    def _normalize(cls, text: Any) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    @classmethod
    def _tokens(cls, text: Any) -> set[str]:
        normalized = cls._normalize(text)
        return {
            token
            for token in cls._TOKEN_RE.findall(normalized)
            if len(token) >= cls.MIN_TOKEN_LENGTH and token not in cls._STOPWORDS
        }

    @classmethod
    def _singular_forms(cls, token: str) -> set[str]:
        forms = {token}
        if token.endswith("ies") and len(token) > 4:
            forms.add(token[:-3] + "y")
        if token.endswith("es") and len(token) > 4:
            forms.add(token[:-2])
        if token.endswith("s") and len(token) > 4:
            forms.add(token[:-1])
        return forms

    @classmethod
    def _semantic_tokens(cls, text: Any) -> set[str]:
        result: set[str] = set()
        for token in cls._tokens(text):
            result.update(cls._singular_forms(token))
        return result

    @classmethod
    def _indicator_text(cls, indicator: Any) -> str:
        name = str(getattr(indicator, "name", "") or "").strip()
        description = str(getattr(indicator, "description", "") or "").strip()
        return f"{name}. {description}".strip()

    @classmethod
    def _recent_indicator_questions(cls, session: Any, indicator_id: str) -> list[str]:
        turns = getattr(session, "turns", None) or []
        result: list[str] = []
        target = str(indicator_id or "").strip()
        for turn in turns:
            if str(getattr(turn, "indicator_id", "") or "").strip() != target:
                continue
            question = getattr(turn, "question", None)
            if isinstance(question, str) and question.strip():
                result.append(question.strip())
        return result[-6:]

    @classmethod
    def _missing_elements(cls, evidence: Any) -> list[str]:
        values = getattr(evidence, "missing_elements", None)
        if not values:
            return []
        if isinstance(values, (list, tuple, set)):
            return [str(value).strip() for value in values if str(value).strip()]
        return [str(values).strip()] if str(values).strip() else []

    def focus_contract(self, *, goal: Any, indicator: Any, goal_state: Any, indicator_id: str) -> dict[str, Any]:
        """Build a bounded, safe evidence-focus contract for prompting."""
        evidence = None
        for item in reversed(getattr(goal_state, "evidence", None) or []):
            if str(getattr(item, "indicator_id", "") or "").strip() == str(indicator_id).strip():
                evidence = item
                break

        indicator_text = self._indicator_text(indicator)
        indicator_terms = self._semantic_tokens(indicator_text)
        recent_questions = self._recent_indicator_questions(self.session, indicator_id)
        recent_terms: set[str] = set()
        if recent_questions:
            recent_terms = self._semantic_tokens(" ".join(recent_questions[-2:]))

        missing = self._missing_elements(evidence)
        missing_terms = self._semantic_tokens(" ".join(missing))

        # Indicator definition is authoritative. Recent questions and missing
        # elements are secondary anchors that help the generator stay coherent
        # without requiring exact wording.
        anchors = indicator_terms | recent_terms | missing_terms
        return {
            "goal_id": str(getattr(goal, "id", "") or "").strip(),
            "indicator_id": str(indicator_id or "").strip(),
            "indicator_terms": sorted(indicator_terms),
            "recent_terms": sorted(recent_terms),
            "missing_terms": sorted(missing_terms),
            "anchors": sorted(anchors),
            "missing_elements_count": len(missing),
        }

    @classmethod
    def prompt_guidance(cls, contract: dict[str, Any]) -> str:
        anchors = ", ".join(contract.get("anchors") or []) or "the exact indicator definition"
        missing = contract.get("missing_elements_count", 0)
        missing_line = (
            "Prioritize the previously identified missing evidence elements."
            if missing
            else "Preserve the same evidence target while varying the task form."
        )
        return (
            "EVIDENCE CONTINUITY CONTRACT: Stay on the selected indicator. "
            "Every part of the question must elicit observable evidence for that "
            "indicator; do not substitute a neighboring programming topic merely "
            "because it has the same Bloom level or difficulty. Ground the question "
            f"in these indicator anchors when applicable: {anchors}. {missing_line} "
            "If the learner is being probed again, change the scenario, operation, "
            "or response format, but preserve the evidence target."
        )

    @classmethod
    def _phrase_match(cls, question: str, indicator: Any) -> bool:
        name = cls._normalize(getattr(indicator, "name", ""))
        if not name:
            return False
        question_norm = cls._normalize(question)
        if len(name) >= 5 and name in question_norm:
            return True
        words = [word for word in cls._TOKEN_RE.findall(name) if word not in cls._STOPWORDS]
        if len(words) >= 2:
            # Allow normal singular/plural variation (e.g. "comprehensions"
            # vs "comprehension") while still requiring every defining word.
            question_terms = cls._semantic_tokens(question_norm)
            return all(
                bool(cls._singular_forms(word) & question_terms)
                for word in words
            )
        return False

    @classmethod
    def assess_question(cls, *, question: str, indicator: Any, contract: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            return {"accepted": False, "score": 0.0, "matched": [], "reason": "empty_question"}

        question_terms = cls._semantic_tokens(question)
        anchor_terms = set(contract.get("anchors") or [])
        if not anchor_terms:
            return {
                "accepted": True,
                "score": 1.0,
                "matched": [],
                "indicator_matches": [],
                "phrase_match": False,
                "reason": "no_meaningful_indicator_anchors",
            }
        matched = sorted(question_terms & anchor_terms)
        phrase_match = cls._phrase_match(question, indicator)

        # The indicator definition has priority. Recent/missing anchors provide
        # continuity when the generator naturally paraphrases the indicator.
        indicator_terms = set(contract.get("indicator_terms") or [])
        indicator_matches = sorted(question_terms & indicator_terms)
        accepted = bool(phrase_match or len(indicator_matches) >= cls.MIN_ANCHOR_MATCHES)
        if not accepted and matched:
            # Secondary anchors alone are accepted only when they are sufficiently
            # distinctive. Two independent recent/missing anchors are a useful
            # signal for paraphrased follow-ups.
            accepted = len(matched) >= 2

        denominator = max(1, len(anchor_terms))
        score = round(min(1.0, len(matched) / denominator), 4)
        if phrase_match:
            score = max(score, 0.9)
        reason = "accepted" if accepted else "no_indicator_evidence_anchor"
        return {
            "accepted": accepted,
            "score": score,
            "matched": matched[:12],
            "indicator_matches": indicator_matches[:12],
            "phrase_match": phrase_match,
            "reason": reason,
        }

    def validate_question(self, *, goal: Any, indicator: Any, goal_state: Any, indicator_id: str, question: str) -> dict[str, Any]:
        contract = self.focus_contract(
            goal=goal,
            indicator=indicator,
            goal_state=goal_state,
            indicator_id=indicator_id,
        )
        result = self.assess_question(
            question=question,
            indicator=indicator,
            contract=contract,
        )
        result.update({
            "version": self.VERSION,
            "goal_id": contract["goal_id"],
            "indicator_id": contract["indicator_id"],
            "anchor_count": len(contract["anchors"]),
        })
        self.state["last"] = {
            "goal_id": contract["goal_id"],
            "indicator_id": contract["indicator_id"],
            "accepted": bool(result["accepted"]),
            "score": result["score"],
            "matched": result["matched"],
            "reason": result["reason"],
        }
        if result["accepted"]:
            self.state["accepted"] = int(self.state.get("accepted", 0)) + 1
        else:
            self.state["rejected"] = int(self.state.get("rejected", 0)) + 1
        return result

    def record_generation(self, *, result: dict[str, Any]) -> None:
        self.state["last"] = {
            "goal_id": result.get("goal_id"),
            "indicator_id": result.get("indicator_id"),
            "accepted": bool(result.get("accepted")),
            "score": result.get("score", 0.0),
            "matched": list(result.get("matched") or [])[:12],
            "reason": result.get("reason", ""),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "accepted": int(self.state.get("accepted", 0)),
            "rejected": int(self.state.get("rejected", 0)),
            "last": dict(self.state.get("last") or {}),
        }
