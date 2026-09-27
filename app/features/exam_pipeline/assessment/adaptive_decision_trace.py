"""Safe, additive audit metadata for adaptive interview decisions.

v9.8 introduces explainability without changing assessment semantics.  The
trace is intentionally limited to identifiers, enums, and bounded numeric
summaries.  Learner answers, raw prompts, generated question text, secrets,
and provider-specific payloads are never included.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class AdaptiveDecisionTrace:
    trace_version: str
    goal_id: str | None
    indicator_id: str | None
    selection_source: str
    target_bloom_level: str
    question_strategy: str
    difficulty: float | None
    generated_difficulty: float | None
    difficulty_reason: str
    criterion_id: str | None
    attempts: int
    achievement_level: float | None
    confidence: float | None
    evidence_strength: float | None
    demonstrated: bool
    previous_decision_status: str | None
    previous_decision_reason: str | None
    previous_coverage: float | None
    previous_mastery: float | None
    previous_confidence: float | None

    TRACE_VERSION = "9.8"
    MAX_TEXT = 240

    @classmethod
    def build(cls, **kwargs: Any) -> "AdaptiveDecisionTrace":
        def text(value: Any, *, max_len: int = cls.MAX_TEXT) -> str:
            return str(value or "").strip()[:max_len]

        def optional_id(value: Any) -> str | None:
            value = text(value, max_len=128)
            return value or None

        def bounded(value: Any, minimum: float = 0.0, maximum: float = 1.0) -> float | None:
            if value is None or isinstance(value, bool):
                return None
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            if not isfinite(number):
                return None
            return round(max(minimum, min(maximum, number)), 4)

        try:
            attempts = max(0, int(kwargs.get("attempts", 0)))
        except (TypeError, ValueError):
            attempts = 0

        achievement = bounded(kwargs.get("achievement_level"), 1.0, 6.0)
        return cls(
            trace_version=cls.TRACE_VERSION,
            goal_id=optional_id(kwargs.get("goal_id")),
            indicator_id=optional_id(kwargs.get("indicator_id")),
            selection_source=text(kwargs.get("selection_source"), max_len=80) or "unknown",
            target_bloom_level=text(kwargs.get("target_bloom_level"), max_len=40),
            question_strategy=text(kwargs.get("question_strategy"), max_len=60),
            difficulty=bounded(kwargs.get("difficulty")),
            generated_difficulty=bounded(kwargs.get("generated_difficulty")),
            difficulty_reason=text(kwargs.get("difficulty_reason")),
            criterion_id=optional_id(kwargs.get("criterion_id")),
            attempts=attempts,
            achievement_level=achievement,
            confidence=bounded(kwargs.get("confidence")),
            evidence_strength=bounded(kwargs.get("evidence_strength")),
            demonstrated=bool(kwargs.get("demonstrated", False)),
            previous_decision_status=optional_id(kwargs.get("previous_decision_status")),
            previous_decision_reason=text(kwargs.get("previous_decision_reason")),
            previous_coverage=bounded(kwargs.get("previous_coverage")),
            previous_mastery=bounded(kwargs.get("previous_mastery")),
            previous_confidence=bounded(kwargs.get("previous_confidence")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_version": self.trace_version,
            "goal_id": self.goal_id,
            "indicator_id": self.indicator_id,
            "selection_source": self.selection_source,
            "target_bloom_level": self.target_bloom_level,
            "question_strategy": self.question_strategy,
            "difficulty": self.difficulty,
            "generated_difficulty": self.generated_difficulty,
            "difficulty_reason": self.difficulty_reason,
            "criterion_id": self.criterion_id,
            "attempts": self.attempts,
            "achievement_level": self.achievement_level,
            "confidence": self.confidence,
            "evidence_strength": self.evidence_strength,
            "demonstrated": self.demonstrated,
            "previous_decision_status": self.previous_decision_status,
            "previous_decision_reason": self.previous_decision_reason,
            "previous_coverage": self.previous_coverage,
            "previous_mastery": self.previous_mastery,
            "previous_confidence": self.previous_confidence,
        }
