"""
app/assessment/scoring_normalizer.py

v9.7 interview-level scoring normalization.

The adaptive interviewer may ask the same indicator more than once.  The
runtime IndicatorState intentionally keeps the latest evaluator state because
navigation and remediation need that live value.  Final assessment scoring,
however, should not depend on which attempt happened to be last.

This module therefore derives an order-independent score from the complete
committed evidence history for each indicator.

Rules
-----
* Evidence is grouped by indicator ID.
* Every committed evaluation contributes according to its evidence quality.
* Quality is derived only from evaluator confidence and evidence strength.
* The contribution is a weighted mean of the discrete achievement levels.
* Evidence order never affects the result.
* If historical evidence is unavailable, the current IndicatorState is used
  as a backward-compatible fallback.
* No runtime state is mutated.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


class ScoringNormalizer:
    """Stateless, deterministic normalization of repeated indicator evidence."""

    MIN_ACHIEVEMENT = 1.0
    MAX_ACHIEVEMENT = 6.0
    MIN_QUALITY_WEIGHT = 0.10

    @classmethod
    def indicator_snapshot(
        cls,
        goal_state: Any,
        indicator: Any,
    ) -> tuple[float, float, float]:
        """Return normalized mastery, confidence, and evidence strength.

        When multiple evaluations exist for the same indicator, the values are
        aggregated from all committed evidence.  Because aggregation is a
        commutative weighted mean, reversing turn order cannot change the
        result.
        """
        indicator_id = cls._indicator_id(indicator)
        evidence = cls._evidence_for_indicator(goal_state, indicator_id)

        if evidence:
            achievement, confidence, strength = cls._aggregate(evidence)
            return (
                cls._achievement_to_mastery(achievement),
                confidence,
                strength,
            )

        # Backward-compatible fallback for restored/legacy state where the
        # indicator has authoritative runtime values but no evidence history.
        achievement = getattr(indicator, "achievement_level", None)
        if achievement is None:
            return 0.0, 0.0, 0.0

        achievement_value = cls._finite_number(achievement, 0.0)
        achievement_value = min(cls.MAX_ACHIEVEMENT, max(cls.MIN_ACHIEVEMENT, achievement_value))
        confidence = cls._probability(getattr(indicator, "confidence", 0.0))
        strength = cls._probability(getattr(indicator, "evidence_strength", 0.0))
        return cls._achievement_to_mastery(achievement_value), confidence, strength

    @classmethod
    def _aggregate(cls, evidence: Iterable[Any]) -> tuple[float, float, float]:
        total_weight = 0.0
        achievement_sum = 0.0
        confidence_sum = 0.0
        strength_sum = 0.0

        for item in evidence:
            achievement = cls._finite_number(
                getattr(item, "achievement_level", None),
                0.0,
            )
            if achievement <= 0.0:
                continue
            achievement = min(cls.MAX_ACHIEVEMENT, max(cls.MIN_ACHIEVEMENT, achievement))

            confidence = cls._probability(getattr(item, "confidence", 0.0))
            strength = cls._probability(getattr(item, "evidence_strength", 0.0))

            # Both dimensions matter.  A single weakly supported evaluation
            # therefore cannot dominate a better-supported repeated attempt.
            quality = max(cls.MIN_QUALITY_WEIGHT, confidence * strength)

            total_weight += quality
            achievement_sum += achievement * quality
            confidence_sum += confidence * quality
            strength_sum += strength * quality

        if total_weight <= 0.0:
            return 0.0, 0.0, 0.0

        return (
            achievement_sum / total_weight,
            confidence_sum / total_weight,
            strength_sum / total_weight,
        )

    @classmethod
    def _evidence_for_indicator(
        cls,
        goal_state: Any,
        indicator_id: str,
    ) -> list[Any]:
        history = getattr(goal_state, "evidence", None)
        if not history:
            return []

        normalized = []
        for item in history:
            if cls._indicator_id(item) == indicator_id:
                normalized.append(item)
        return normalized

    @staticmethod
    def _indicator_id(value: Any) -> str:
        raw = getattr(value, "indicator_id", None)
        if raw is None:
            raw = getattr(value, "id", None)
        return str(raw).strip() if raw is not None else ""

    @classmethod
    def _achievement_to_mastery(cls, value: float) -> float:
        if value <= 0.0:
            return 0.0
        return min(1.0, max(0.0, value / cls.MAX_ACHIEVEMENT))

    @staticmethod
    def _finite_number(value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return numeric if math.isfinite(numeric) else default

    @staticmethod
    def _probability(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(numeric):
            return 0.0
        return min(1.0, max(0.0, numeric))
