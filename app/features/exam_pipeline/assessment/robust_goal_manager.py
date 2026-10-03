"""Goal-level adaptive orchestration for v10.6."""
from __future__ import annotations
from typing import Any
from .goal_time_manager import GoalTimeManager

class GoalManager:
    VERSION = "10.6"
    METADATA_KEY = "robust_goal_management"
    MIN_QUESTIONS_PER_GOAL = 4
    FAILURE_CONSECUTIVE_WEAK_ANSWERS = 3
    CERTAINTY_THRESHOLD = 0.85
    MIN_DIFFICULTY = 0.20
    MAX_DIFFICULTY = 0.95
    STRONG_STEP = 0.12
    MEDIUM_STEP = 0.06
    WEAK_STEP = 0.12

    def __init__(self, session: Any):
        if session is None:
            raise ValueError("GoalManager requires a session.")
        self.session = session
        self.time_manager = GoalTimeManager(session)
        self._ensure_state()

    def _ensure_state(self):
        metadata = getattr(self.session, "metadata", None)
        if not isinstance(metadata, dict):
            # Defensive compatibility: navigation GoalManager may be tested
            # independently with a list; the robust manager is session-bound.
            raise TypeError("Robust GoalManager requires a session with dict metadata.")
        state = metadata.get(self.METADATA_KEY)
        if not isinstance(state, dict) or state.get("version") != self.VERSION:
            state = {"version": self.VERSION, "minimum_questions_per_goal": self.MIN_QUESTIONS_PER_GOAL,
                     "certainty_threshold": self.CERTAINTY_THRESHOLD,
                     "failure_consecutive_weak_answers": self.FAILURE_CONSECUTIVE_WEAK_ANSWERS,
                     "goals": {}}
            metadata[self.METADATA_KEY] = state
        state.setdefault(
            "failure_consecutive_weak_answers",
            self.FAILURE_CONSECUTIVE_WEAK_ANSWERS,
        )
        self.state = state

    @staticmethod
    def _goal_id(goal_state):
        return str(getattr(getattr(goal_state, "goal", None), "id", "")).strip()

    @classmethod
    def _clamp(cls, value):
        try: value = float(value)
        except (TypeError, ValueError): value = 0.5
        return max(cls.MIN_DIFFICULTY, min(cls.MAX_DIFFICULTY, value))

    @classmethod
    def _prob(cls, value):
        try: return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError): return 0.0

    @classmethod
    def _initial_difficulty(cls, goal_state):
        return cls._clamp(getattr(getattr(goal_state, "goal", None), "difficulty", 0.5))

    def _entry(self, goal_state):
        gid = self._goal_id(goal_state)
        if not gid: raise ValueError("GoalState must contain a stable goal id.")
        return self.state["goals"].setdefault(gid, {
            "question_count": 0, "difficulty": self._initial_difficulty(goal_state),
            "last_band": None, "last_performance": None, "last_confidence": 0.0,
            "last_evidence_strength": 0.0, "last_demonstrated": False,
            "direction": "hold", "reason": "initial",
            "weak_streak": 0,
        })

    @classmethod
    def classify_evidence(cls, evidence):
        try: achievement = int(getattr(evidence, "achievement_level", 1))
        except (TypeError, ValueError): achievement = 1
        confidence = cls._prob(getattr(evidence, "confidence", 0.0))
        strength = cls._prob(getattr(evidence, "evidence_strength", 0.0))
        demonstrated = bool(getattr(evidence, "indicator_demonstrated", False))
        if achievement >= 5 and demonstrated and confidence >= .70 and strength >= .70: return "strong"
        if achievement >= 3 and confidence >= .55 and strength >= .55: return "medium"
        return "weak"

    @classmethod
    def performance_score(cls, evidence):
        try: achievement = int(getattr(evidence, "achievement_level", 1))
        except (TypeError, ValueError): achievement = 1
        return round(.70 * max(0.0, min(1.0, (achievement - 1) / 5.0)) +
                     .15 * cls._prob(getattr(evidence, "confidence", 0.0)) +
                     .15 * cls._prob(getattr(evidence, "evidence_strength", 0.0)), 4)

    def observe(self, goal_state, evidence):
        entry = self._entry(goal_state)
        entry["question_count"] = int(entry.get("question_count", 0)) + 1
        band = self.classify_evidence(evidence)
        previous = self._clamp(entry.get("difficulty", self._initial_difficulty(goal_state)))
        previous_weak_streak = int(entry.get("weak_streak", 0) or 0)
        if band == "strong":
            weak_streak = 0
            new, direction, reason = self._clamp(previous + self.STRONG_STEP), "increase", "strong answer -> increase question complexity"
        elif band == "medium":
            weak_streak = 0
            new, direction, reason = self._clamp(previous + self.MEDIUM_STEP), "increase", "medium answer -> increase question complexity gradually"
        else:
            weak_streak = previous_weak_streak + 1
            new, direction, reason = self._clamp(previous - self.WEAK_STEP), "decrease", "weak answer -> simplify the next question"
        if new == previous: direction = "hold"
        entry.update(question_count=entry["question_count"], difficulty=round(new,4), last_band=band,
                     last_performance=self.performance_score(evidence),
                     last_confidence=self._prob(getattr(evidence,"confidence",0.0)),
                     last_evidence_strength=self._prob(getattr(evidence,"evidence_strength",0.0)),
                     last_demonstrated=bool(getattr(evidence,"indicator_demonstrated",False)),
                     direction=direction, reason=reason, weak_streak=weak_streak)
        self._sync_time(goal_state)
        return self.snapshot(goal_state)

    def question_count(self, goal_state): return max(0, int(self._entry(goal_state).get("question_count",0)))
    def minimum_questions_met(self, goal_state): return self.question_count(goal_state) >= int(self.state.get("minimum_questions_per_goal",4))
    def target_difficulty(self, goal_state): return self._clamp(self._entry(goal_state).get("difficulty", self._initial_difficulty(goal_state)))
    def certainty(self, evidence):
        threshold=float(self.state.get("certainty_threshold",self.CERTAINTY_THRESHOLD))
        return self._prob(getattr(evidence,"confidence",0.0)) >= threshold and self._prob(getattr(evidence,"evidence_strength",0.0)) >= threshold

    def failure_threshold(self) -> int:
        try:
            value = int(self.state.get(
                "failure_consecutive_weak_answers",
                self.FAILURE_CONSECUTIVE_WEAK_ANSWERS,
            ))
        except (TypeError, ValueError):
            value = self.FAILURE_CONSECUTIVE_WEAK_ANSWERS
        return max(3, min(4, value))

    def consecutive_weak_answers(self, goal_state) -> int:
        gid = self._goal_id(goal_state)
        entry = self.state.get("goals", {}).get(gid, {})
        return max(0, int(entry.get("weak_streak", 0) or 0))

    def failure_threshold_reached(self, goal_state) -> bool:
        return self.consecutive_weak_answers(goal_state) >= self.failure_threshold()

    def terminal_allowed(self, goal_state, decision, evidence):
        """Gate terminal decisions while allowing bounded weak-answer failure.

        Successful completion retains the existing four-question minimum and
        certainty gate. A goal may now fail earlier when the learner produces
        the configured consecutive weak-answer streak (default: 3). This is a
        goal-failure policy, not an interview-completion policy; navigation then
        moves to the next available goal.
        """
        status = str(getattr(getattr(decision,"status", ""), "value", getattr(decision,"status", ""))).lower()
        terminal = bool(getattr(decision,"is_complete",False) or getattr(decision,"is_failed",False) or status in {"complete","completed","passed","pass","goal_completed","failed","failure","exhausted","goal_exhausted"})
        if not terminal:
            return False

        if getattr(decision,"is_complete",False) or status in {"complete","completed","passed","pass","goal_completed"}:
            if not self.minimum_questions_met(goal_state):
                return False
            return self.certainty(evidence)

        if self.failure_threshold_reached(goal_state):
            return True

        # Preserve the legacy high-certainty failure path, but keep the
        # original minimum-question boundary for it.
        if not self.minimum_questions_met(goal_state):
            return False
        confidence = self._prob(getattr(evidence,"confidence",0.0))
        strength = self._prob(getattr(evidence,"evidence_strength",0.0))
        if confidence >= self.CERTAINTY_THRESHOLD and strength >= self.CERTAINTY_THRESHOLD:
            return True
        gid = self._goal_id(goal_state)
        entry = self.state.get("goals",{}).get(gid,{})
        band = entry.get("last_band")
        return band == "weak" and not bool(entry.get("last_demonstrated", False))

    def indicator_for_minimum(self, goal_state, preferred_indicator_id=None):
        indicators=getattr(goal_state,"indicators",{}) or {}
        preferred=str(preferred_indicator_id or "").strip()
        if preferred and preferred in indicators: return indicators[preferred]
        current=str(getattr(goal_state,"current_indicator_id","") or "").strip()
        if current and current in indicators: return indicators[current]
        values=list(indicators.values())
        return min(values,key=lambda i:int(getattr(i,"attempts",0) or 0)) if values else None

    def _sync_time(self, goal_state):
        gid=self._goal_id(goal_state)
        if not gid:return
        self.time_manager.ensure_goal_started(gid)
        snap=self.time_manager.snapshot(gid)
        timing=(snap.get("goals",{}) or {}).get(gid,{})
        for field,key in (("time_budget_seconds","budget_seconds"),("time_elapsed_seconds","elapsed_seconds"),("time_remaining_seconds","remaining_seconds")):
            if hasattr(goal_state,field): setattr(goal_state,field,float(timing.get(key,0.0) or 0.0))
        if hasattr(goal_state,"time_started_at"):
            goal_state.time_started_at=self.time_manager.state.get("started_goals",{}).get(gid)

    def snapshot(self, goal_state=None):
        gid=self._goal_id(goal_state) if goal_state is not None else None
        for state in self.time_manager._goal_states():
            if self._goal_id(state): self._entry(state)
        ts=self.time_manager.snapshot(gid); goals={}
        for id_,data in self.state["goals"].items():
            timing=(ts.get("goals",{}) or {}).get(id_,{})
            goals[id_] = {**data,"time_budget_seconds":timing.get("budget_seconds",0.0),"time_elapsed_seconds":timing.get("elapsed_seconds",0.0),"time_remaining_seconds":timing.get("remaining_seconds",0.0),"time_status":timing.get("status")}
        return {"version":self.VERSION,"minimum_questions_per_goal":int(self.state.get("minimum_questions_per_goal",4)),"certainty_threshold":float(self.state.get("certainty_threshold",.85)),"failure_consecutive_weak_answers":self.failure_threshold(),"current_goal_id":gid,"goals":goals,"time":ts}
