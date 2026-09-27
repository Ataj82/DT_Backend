"""v10.1 safe ABET outcome evidence traceability.

This module is reporting/audit-only. It builds an explicit, bounded chain:
Goal -> Indicator -> ABET Outcome -> Learning Outcome -> Criterion ->
Question Decision -> Evidence -> Normalized Indicator Score -> Final Outcome.

It intentionally does not expose learner answers, raw questions, prompts,
LLM payloads, or provider data.
"""
from __future__ import annotations

from typing import Any

from ..abet.attainment import build_attainment
from ..abet.service import ABETService
from .scoring_normalizer import ScoringNormalizer


class ABETTraceability:
    VERSION = "10.1"
    MAX_TEXT = 300

    @classmethod
    def build(cls, session: Any) -> dict[str, Any]:
        raw = (getattr(session, "metadata", {}) or {}).get("abet", {}).get("plan")
        if not raw:
            return {"version": cls.VERSION, "enabled": False, "reason": "No ABET assessment plan is attached."}

        plan = ABETService._from_dict(raw)
        attainment = build_attainment(plan, session)
        goals = {str(getattr(g, "id", "")): g for g in (getattr(getattr(session, "goal_model", None), "goals", None) or [])}
        goal_states = getattr(session, "goal_states", None) or {}
        criteria = {c.id: c for c in plan.criteria}
        los = {x.id: x for x in plan.learning_outcomes}
        outcomes = {x.id: x for x in plan.outcomes}
        rubrics = {x.id: x for x in plan.rubrics}

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for turn in getattr(session, "turns", []) or []:
            if not getattr(turn, "answered", False):
                continue
            meta = getattr(turn, "metadata", {}) or {}
            target = ((meta.get("abet") or {}).get("target") or {})
            criterion_id = cls._id(target.get("criterion_id"))
            if not criterion_id or criterion_id not in criteria:
                continue

            criterion = criteria[criterion_id]
            goal_id = cls._id(getattr(turn, "goal_id", None))
            indicator_id = cls._id(getattr(turn, "indicator_id", None))
            if not goal_id or not indicator_id:
                continue

            lo_id = cls._resolve_lo_id(criterion, los, goal_id)
            outcome_id = cls._resolve_outcome_id(criterion, lo_id, los)
            goal_state = goal_states.get(goal_id)
            indicator = cls._find_indicator(goal_state, indicator_id)
            normalized = (0.0, 0.0, 0.0)
            if goal_state is not None and indicator is not None:
                normalized = ScoringNormalizer.indicator_snapshot(goal_state, indicator)

            assessment = meta.get("assessment") or {}
            decision = meta.get("adaptive_decision_trace") or {}
            evidence = {
                "achievement_level": cls._number(assessment.get("achievement_level")),
                "confidence": cls._probability(assessment.get("confidence", assessment.get("assessment_confidence", 0.0))),
                "evidence_strength": cls._probability(assessment.get("evidence_strength", 0.0)),
                "demonstrated": bool(assessment.get("indicator_demonstrated", assessment.get("demonstrated", False))),
                "missing_element_count": len(assessment.get("missing_elements") or []),
            }

            key = (goal_id, indicator_id, criterion_id, str(getattr(turn, "index", "")))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "turn_index": getattr(turn, "index", None),
                "goal_id": goal_id,
                "goal_title": cls._text(getattr(goals.get(goal_id), "title", "")),
                "indicator_id": indicator_id,
                "indicator_name": cls._text(getattr(indicator, "name", "") if indicator is not None else ""),
                "outcome": cls._entity(outcomes.get(outcome_id), "outcome"),
                "learning_outcome": cls._entity(los.get(lo_id), "learning_outcome"),
                "criterion": cls._criterion(criterion, rubrics.get(criterion.rubric_id)),
                "question_decision": {
                    "selection_source": cls._text(decision.get("selection_source"), 80),
                    "target_bloom_level": cls._text(decision.get("target_bloom_level"), 40),
                    "question_strategy": cls._text(decision.get("question_strategy"), 80),
                    "difficulty": cls._probability(decision.get("difficulty")),
                    "difficulty_reason": cls._text(decision.get("difficulty_reason")),
                    "previous_decision_status": cls._text(decision.get("previous_decision_status"), 80) or None,
                },
                "evidence": evidence,
                "normalized_indicator_score": {
                    "mastery": round(normalized[0], 4),
                    "confidence": round(normalized[1], 4),
                    "evidence_strength": round(normalized[2], 4),
                },
            })

        # Final outcome values come from the existing ABET attainment engine;
        # only safe summary values are exposed here.
        final = {
            "criteria": {},
            "learning_outcomes": {},
            "outcomes": {},
            "completed": bool(attainment.get("completed", False)),
        }
        for cid, value in (attainment.get("criteria") or {}).items():
            final["criteria"][cid] = cls._summary(value)
        for lid, value in (attainment.get("learning_outcomes") or {}).items():
            final["learning_outcomes"][lid] = cls._summary(value)
        for oid, value in (attainment.get("outcomes") or {}).items():
            final["outcomes"][oid] = cls._summary(value)

        return {
            "version": cls.VERSION,
            "enabled": True,
            "plan_id": cls._id(raw.get("id")),
            "trace_count": len(rows),
            "traces": rows,
            "final_outcome": final,
        }

    @classmethod
    def _resolve_lo_id(cls, criterion: Any, los: dict[str, Any], goal_id: str) -> str | None:
        if getattr(criterion, "learning_outcome_id", None) in los:
            return criterion.learning_outcome_id
        for lo in los.values():
            if goal_id in getattr(lo, "goal_ids", []):
                return lo.id
        return None

    @classmethod
    def _resolve_outcome_id(cls, criterion: Any, lo_id: str | None, los: dict[str, Any]) -> str | None:
        if getattr(criterion, "outcome_id", None):
            return criterion.outcome_id
        lo = los.get(lo_id) if lo_id else None
        return getattr(lo, "outcome_id", None)

    @staticmethod
    def _find_indicator(goal_state: Any, indicator_id: str):
        indicators = getattr(goal_state, "indicators", None) if goal_state is not None else None
        if isinstance(indicators, dict):
            return indicators.get(indicator_id)
        for item in indicators or []:
            if str(getattr(item, "id", "")).strip() == indicator_id:
                return item
        return None

    @classmethod
    def _criterion(cls, criterion: Any, rubric: Any) -> dict[str, Any]:
        return {
            "id": cls._id(criterion.id),
            "code": cls._text(criterion.code, 80),
            "description": cls._text(criterion.description),
            "minimum_level": int(getattr(criterion, "minimum_level", 1)),
            "weight": float(getattr(criterion, "weight", 1.0)),
            "rubric_id": cls._id(getattr(criterion, "rubric_id", None)) or None,
            "rubric_name": cls._text(getattr(rubric, "name", ""), 120) if rubric else "",
        }

    @classmethod
    def _entity(cls, value: Any, kind: str) -> dict[str, Any]:
        if value is None:
            return {"id": None, "code": "", "title": "", "type": kind}
        return {"id": cls._id(getattr(value, "id", None)) or None, "code": cls._text(getattr(value, "code", ""), 80), "title": cls._text(getattr(value, "title", ""), 180), "type": kind}

    @classmethod
    def _summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {"attainment": round(float(value.get("attainment", 0.0)), 4), "coverage": round(float(value.get("coverage", 0.0)), 4), "status": cls._text(value.get("status"), 40)}

    @staticmethod
    def _id(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _text(cls, value: Any, limit: int = MAX_TEXT) -> str:
        return str(value or "").strip()[:limit]

    @staticmethod
    def _probability(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
