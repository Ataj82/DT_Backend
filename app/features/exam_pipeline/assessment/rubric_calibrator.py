"""v10.0 evidence-to-rubric calibration and scoring reliability.

This module is diagnostic only. It never changes evaluator output, GoalState,
scoring normalization, completion, or navigation. It creates a bounded,
serializable trace showing how committed evidence supports the configured
indicator rubric (the indicator description) and flags internally inconsistent
score/evidence combinations.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .scoring_normalizer import ScoringNormalizer


@dataclass(frozen=True, slots=True)
class RubricCalibration:
    version: str
    indicators: list[dict[str, Any]]
    issue_count: int
    high_severity_count: int

    VERSION = "10.0"
    MAX_TEXT = 300

    @classmethod
    def build(cls, goal_state: Any) -> "RubricCalibration":
        rows: list[dict[str, Any]] = []
        issue_count = 0
        high_count = 0
        indicators = getattr(goal_state, "indicators", None) or {}
        evidence = getattr(goal_state, "evidence", None) or []

        values = indicators.values() if hasattr(indicators, "values") else indicators
        for indicator in values:
            indicator_id = cls._text(getattr(indicator, "id", ""), 128)
            if not indicator_id:
                continue
            description = cls._text(getattr(indicator, "description", ""), cls.MAX_TEXT)
            history = [item for item in evidence if cls._indicator_id(item) == indicator_id]
            normalized_mastery, normalized_confidence, normalized_strength = (
                ScoringNormalizer.indicator_snapshot(goal_state, indicator)
            )
            normalized_achievement = round(normalized_mastery * 6.0, 4)
            attempts = []
            issues: list[dict[str, str]] = []
            for index, item in enumerate(history, start=1):
                achievement = cls._number(getattr(item, "achievement_level", None))
                confidence = cls._probability(getattr(item, "confidence", 0.0))
                strength = cls._probability(getattr(item, "evidence_strength", 0.0))
                demonstrated = bool(getattr(item, "indicator_demonstrated", False))
                missing = [cls._text(x, 160) for x in (getattr(item, "missing_elements", None) or []) if cls._text(x, 160)]
                attempt = {
                    "attempt": index,
                    "achievement_level": round(achievement, 4) if achievement is not None else None,
                    "confidence": round(confidence, 4),
                    "evidence_strength": round(strength, 4),
                    "demonstrated": demonstrated,
                    "missing_element_count": len(missing),
                    "missing_elements": missing[:8],
                    "rubric_reference": description,
                }
                attempts.append(attempt)

                if achievement is not None and achievement >= 5.0 and strength < 0.45:
                    issues.append({"code": "high_score_weak_evidence", "severity": "high"})
                if demonstrated and strength < 0.30:
                    issues.append({"code": "demonstrated_weak_evidence", "severity": "high"})
                if achievement is not None and achievement >= 5.0 and missing:
                    issues.append({"code": "high_score_with_missing_elements", "severity": "medium"})
                if achievement is not None and achievement <= 2.0 and demonstrated:
                    issues.append({"code": "low_score_marked_demonstrated", "severity": "medium"})

            # Deduplicate issue codes while preserving severity.
            unique: dict[str, str] = {}
            for issue in issues:
                unique[issue["code"]] = issue["severity"]
            issue_list = [{"code": code, "severity": severity} for code, severity in unique.items()]
            issue_count += len(issue_list)
            high_count += sum(1 for item in issue_list if item["severity"] == "high")

            rows.append({
                "indicator_id": indicator_id,
                "rubric_source": "GoalIndicator.description",
                "rubric_reference": description,
                "evidence_count": len(history),
                "attempts": attempts,
                "normalized_achievement_level": normalized_achievement,
                "normalized_mastery": round(normalized_mastery, 4),
                "normalized_confidence": round(normalized_confidence, 4),
                "normalized_evidence_strength": round(normalized_strength, 4),
                "issues": issue_list,
            })

        return cls(
            version=cls.VERSION,
            indicators=rows,
            issue_count=issue_count,
            high_severity_count=high_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "indicator_count": len(self.indicators),
            "issue_count": self.issue_count,
            "high_severity_count": self.high_severity_count,
            "indicators": self.indicators,
        }

    @staticmethod
    def _indicator_id(value: Any) -> str:
        raw = getattr(value, "indicator_id", None)
        return str(raw).strip() if raw is not None else ""

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return str(value or "").strip()[:limit]

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) else None

    @staticmethod
    def _probability(value: Any) -> float:
        number = RubricCalibration._number(value)
        if number is None:
            return 0.0
        return max(0.0, min(1.0, number))
