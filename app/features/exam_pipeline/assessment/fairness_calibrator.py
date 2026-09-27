"""v9.9 fairness and scoring calibration diagnostics.

This module is deliberately diagnostic-only.  It does not change scores,
completion, navigation, difficulty, or evaluator outputs.

Because the current assessment model does not carry protected-group labels,
v9.9 provides *procedural fairness* diagnostics: it identifies indicators
whose repeated evidence is unusually inconsistent and compares the latest
runtime state with the order-independent v9.7 normalized result.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .scoring_normalizer import ScoringNormalizer


@dataclass(frozen=True, slots=True)
class CalibrationFinding:
    indicator_id: str
    attempts: int
    achievement_range: float
    confidence_range: float
    evidence_strength_range: float
    latest_achievement: float | None
    normalized_achievement: float | None
    score_delta: float
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "attempts": self.attempts,
            "achievement_range": round(self.achievement_range, 4),
            "confidence_range": round(self.confidence_range, 4),
            "evidence_strength_range": round(self.evidence_strength_range, 4),
            "latest_achievement": self.latest_achievement,
            "normalized_achievement": self.normalized_achievement,
            "score_delta": round(self.score_delta, 4),
            "severity": self.severity,
        }


class FairnessCalibrator:
    """Stateless diagnostics for repeated-evidence scoring consistency."""

    VERSION = "9.9"
    ACHIEVEMENT_RANGE_THRESHOLD = 2.0
    PROBABILITY_RANGE_THRESHOLD = 0.35
    SCORE_DELTA_THRESHOLD = 1.0

    @classmethod
    def calibrate_goal(cls, goal_state: Any) -> dict[str, Any]:
        indicators = getattr(goal_state, "indicators", None) or {}
        findings: list[CalibrationFinding] = []
        assessed = 0
        repeated = 0

        for indicator in indicators.values():
            indicator_id = str(getattr(indicator, "id", "") or "").strip()
            if not indicator_id:
                continue
            evidence = cls._evidence(goal_state, indicator_id)
            if not evidence:
                continue
            assessed += 1
            if len(evidence) < 2:
                continue
            repeated += 1

            achievements = cls._numbers(evidence, "achievement_level", 1.0, 6.0)
            confidences = cls._numbers(evidence, "confidence", 0.0, 1.0)
            strengths = cls._numbers(evidence, "evidence_strength", 0.0, 1.0)
            if not achievements:
                continue

            normalized_mastery, _, _ = ScoringNormalizer.indicator_snapshot(goal_state, indicator)
            normalized_achievement = normalized_mastery * ScoringNormalizer.MAX_ACHIEVEMENT
            latest = cls._latest_achievement(indicator)
            score_delta = abs((latest or 0.0) - normalized_achievement)
            achievement_range = max(achievements) - min(achievements)
            confidence_range = (max(confidences) - min(confidences)) if confidences else 0.0
            strength_range = (max(strengths) - min(strengths)) if strengths else 0.0

            if score_delta >= cls.SCORE_DELTA_THRESHOLD or achievement_range >= cls.ACHIEVEMENT_RANGE_THRESHOLD:
                severity = "high"
            elif confidence_range >= cls.PROBABILITY_RANGE_THRESHOLD or strength_range >= cls.PROBABILITY_RANGE_THRESHOLD:
                severity = "medium"
            else:
                continue

            findings.append(CalibrationFinding(
                indicator_id=indicator_id,
                attempts=len(evidence),
                achievement_range=achievement_range,
                confidence_range=confidence_range,
                evidence_strength_range=strength_range,
                latest_achievement=latest,
                normalized_achievement=round(normalized_achievement, 4),
                score_delta=score_delta,
                severity=severity,
            ))

        return {
            "calibration_version": cls.VERSION,
            "diagnostic_only": True,
            "protected_group_analysis": False,
            "assessed_indicators": assessed,
            "repeated_indicators": repeated,
            "flagged_indicators": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "medium_severity": sum(1 for f in findings if f.severity == "medium"),
            "findings": [f.to_dict() for f in findings],
        }

    @staticmethod
    def _evidence(goal_state: Any, indicator_id: str) -> list[Any]:
        history = getattr(goal_state, "evidence", None) or []
        return [item for item in history if str(getattr(item, "indicator_id", "") or "").strip() == indicator_id]

    @staticmethod
    def _numbers(items: list[Any], field: str, low: float, high: float) -> list[float]:
        values = []
        for item in items:
            try:
                value = float(getattr(item, field, 0.0))
            except (TypeError, ValueError):
                continue
            if isfinite(value):
                values.append(max(low, min(high, value)))
        return values

    @staticmethod
    def _latest_achievement(indicator: Any) -> float | None:
        value = getattr(indicator, "achievement_level", None)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if isfinite(value) and value > 0 else None
