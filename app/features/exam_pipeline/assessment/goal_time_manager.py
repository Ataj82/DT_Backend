"""
Goal-specific time budgeting for time-forced interviews.

The global interview deadline remains authoritative. This component adds a
second, deterministic layer: every goal receives its own initial budget based
on the goal's assessment complexity, and unused time from a completed/failed
goal is returned to the remaining-goal pool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import floor
from typing import Any


class GoalTimeManager:
    VERSION = "10.5"
    METADATA_KEY = "goal_time_management"
    MIN_GOAL_SECONDS = 15.0

    def __init__(self, session: Any):
        if session is None:
            raise ValueError("GoalTimeManager requires a session.")
        self.session = session
        self._ensure_state()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _duration(self) -> float:
        configuration = getattr(self.session, "configuration", None)
        value = None
        if isinstance(configuration, dict):
            value = configuration.get("duration_seconds")
            if value is None and configuration.get("max_minutes") is not None:
                value = float(configuration.get("max_minutes")) * 60.0
        elif configuration is not None:
            value = getattr(configuration, "duration_seconds", None)
            if value is None and hasattr(configuration, "max_minutes"):
                minutes = getattr(configuration, "max_minutes", None)
                if minutes is not None:
                    value = float(minutes) * 60.0
        if value is None:
            meta = getattr(self.session, "metadata", {}) or {}
            value = meta.get("duration_seconds")
        try:
            return max(30.0, float(value))
        except (TypeError, ValueError):
            return 600.0

    def _elapsed(self) -> float:
        started = getattr(self.session, "started_at", None)
        if started is None:
            return 0.0
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (self._now() - started).total_seconds())

    def _goal_states(self) -> list[Any]:
        states = getattr(self.session, "goal_states", {})
        if isinstance(states, dict):
            return list(states.values())
        return list(states or [])

    @staticmethod
    def _goal_id(state: Any) -> str:
        goal = getattr(state, "goal", None)
        return str(getattr(goal, "id", "")).strip()

    @staticmethod
    def _weight(state: Any) -> float:
        goal = getattr(state, "goal", None)
        importance = max(0.10, float(getattr(goal, "importance", 1.0) or 1.0))
        difficulty = min(1.0, max(0.0, float(getattr(goal, "difficulty", 0.5) or 0.5)))
        estimated_questions = max(1.0, float(getattr(goal, "estimated_questions", 3) or 3))
        indicators = getattr(goal, "indicators", None) or []
        try:
            indicator_count = max(1.0, float(len(indicators)))
        except TypeError:
            indicator_count = 1.0
        # Difficulty and evidence surface area increase the expected time;
        # importance and estimated question count preserve goal semantics.
        return importance * (0.75 + difficulty) * (0.75 + estimated_questions / 3.0) * (0.75 + indicator_count / 2.0)

    @classmethod
    def validate_configuration(cls, configuration: Any, goals: list[Any]) -> None:
        """Validate an explicit allocation before a session is persisted."""
        raw = getattr(configuration, "goal_time_allocations_seconds", None)
        if raw is None:
            return
        if not isinstance(raw, dict):
            raise ValueError("goal_time_allocations_seconds must be an object mapping goal IDs to seconds.")
        expected = {str(getattr(goal, "id", "")).strip() for goal in goals if str(getattr(goal, "id", "")).strip()}
        supplied = {str(key).strip() for key in raw}
        unknown = sorted(supplied - expected)
        missing = sorted(expected - supplied)
        if unknown:
            raise ValueError("goal_time_allocations_seconds contains unknown goal IDs: " + ", ".join(unknown))
        if missing:
            raise ValueError("goal_time_allocations_seconds must specify every goal; missing: " + ", ".join(missing))
        values = {}
        for goal_id in expected:
            try:
                value = float(raw[goal_id])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid time allocation for goal '{goal_id}'.") from exc
            if value <= 0:
                raise ValueError(f"Time allocation for goal '{goal_id}' must be greater than zero.")
            values[goal_id] = value
        duration = getattr(configuration, "duration_seconds", None)
        if duration is None:
            duration = float(getattr(configuration, "max_minutes", 30) or 30) * 60.0
        duration = max(30.0, float(duration))
        total = sum(values.values())
        if abs(total - duration) > 0.01:
            raise ValueError(
                "Explicit goal time allocations must sum exactly to "
                f"the interview duration ({duration:.2f} seconds); received {total:.2f}."
            )

    def _explicit_allocations(self, states: list[Any]) -> dict[str, float] | None:
        configuration = getattr(self.session, "configuration", None)
        raw = getattr(configuration, "goal_time_allocations_seconds", None)
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("goal_time_allocations_seconds must be an object mapping goal IDs to seconds.")

        expected = {self._goal_id(state) for state in states if self._goal_id(state)}
        supplied = {str(key).strip() for key in raw}
        unknown = sorted(supplied - expected)
        missing = sorted(expected - supplied)
        if unknown:
            raise ValueError(
                "goal_time_allocations_seconds contains unknown goal IDs: "
                + ", ".join(unknown)
            )
        if missing:
            raise ValueError(
                "goal_time_allocations_seconds must specify every goal; missing: "
                + ", ".join(missing)
            )

        allocations: dict[str, float] = {}
        for goal_id in expected:
            try:
                value = float(raw[goal_id])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid time allocation for goal '{goal_id}'.") from exc
            if value <= 0:
                raise ValueError(f"Time allocation for goal '{goal_id}' must be greater than zero.")
            allocations[goal_id] = round(value, 2)

        total = self._duration()
        if abs(sum(allocations.values()) - total) > 0.01:
            raise ValueError(
                "Explicit goal time allocations must sum exactly to "
                f"the interview duration ({total:.2f} seconds); "
                f"received {sum(allocations.values()):.2f}."
            )
        return allocations

    @classmethod
    def _allocate(cls, total: float, states: list[Any]) -> dict[str, float]:
        if not states or total <= 0:
            return {}
        ids = [cls._goal_id(s) for s in states]
        weights = [cls._weight(s) for s in states]
        weight_sum = sum(weights) or float(len(states))
        raw = [total * w / weight_sum for w in weights]
        if total >= cls.MIN_GOAL_SECONDS * len(states):
            # Apply a floor, then distribute the residual proportionally.
            budgets = [max(cls.MIN_GOAL_SECONDS, value) for value in raw]
            excess = sum(budgets) - total
            if excess > 0:
                reducible = sum(max(0.0, b - cls.MIN_GOAL_SECONDS) for b in budgets)
                if reducible > 0:
                    budgets = [b - excess * max(0.0, b - cls.MIN_GOAL_SECONDS) / reducible for b in budgets]
        else:
            budgets = raw
        # Preserve the exact total to the centisecond while avoiding float drift.
        rounded = [round(max(0.0, b), 2) for b in budgets]
        delta = round(total - sum(rounded), 2)
        if rounded:
            rounded[-1] = round(max(0.0, rounded[-1] + delta), 2)
        return dict(zip(ids, rounded))

    def _ensure_state(self) -> None:
        metadata = getattr(self.session, "metadata", None)
        if metadata is None:
            metadata = {}
            self.session.metadata = metadata
        state = metadata.get(self.METADATA_KEY)
        if not isinstance(state, dict) or state.get("version") != self.VERSION:
            goals = self._goal_states()
            explicit = self._explicit_allocations(goals)
            allocations = explicit if explicit is not None else self._allocate(self._duration(), goals)
            metadata[self.METADATA_KEY] = {
                "version": self.VERSION,
                "total_duration_seconds": self._duration(),
                "allocation_mode": "explicit" if explicit is not None else "auto",
                "initial_allocations": allocations.copy(),
                "allocations": allocations.copy(),
                "started_goals": {},
                "finished_goals": {},
                "redistributed_seconds": 0.0,
            }

    @property
    def state(self) -> dict[str, Any]:
        return self.session.metadata[self.METADATA_KEY]

    def ensure_goal_started(self, goal_id: str) -> None:
        goal_id = str(goal_id).strip()
        if not goal_id:
            return
        started = self.state["started_goals"]
        if goal_id not in started:
            started[goal_id] = self._now().isoformat()

    def _goal_elapsed(self, goal_id: str) -> float:
        value = self.state["started_goals"].get(goal_id)
        if not value:
            return 0.0
        started = datetime.fromisoformat(value)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (self._now() - started).total_seconds())

    def goal_budget(self, goal_id: str) -> float:
        return max(0.0, float(self.state["allocations"].get(str(goal_id).strip(), 0.0)))

    def goal_elapsed(self, goal_id: str) -> float:
        return min(self.goal_budget(goal_id), self._goal_elapsed(str(goal_id).strip()))

    def goal_remaining(self, goal_id: str) -> float:
        return max(0.0, self.goal_budget(goal_id) - self.goal_elapsed(goal_id))

    def global_remaining(self) -> float:
        return max(0.0, self._duration() - self._elapsed())

    def goal_expired(self, goal_id: str) -> bool:
        return self.goal_remaining(goal_id) <= 0.0

    def finish_goal(self, goal_id: str, *, outcome: str) -> dict[str, float | str]:
        goal_id = str(goal_id).strip()
        if not goal_id:
            return {"goal_id": goal_id, "outcome": outcome, "budget_seconds": 0.0, "elapsed_seconds": 0.0, "remaining_seconds": 0.0}
        self.ensure_goal_started(goal_id)
        budget = self.goal_budget(goal_id)
        elapsed_raw = self._goal_elapsed(goal_id)
        elapsed = min(budget, elapsed_raw)
        remaining = max(0.0, budget - elapsed)
        finished = self.state["finished_goals"]
        if goal_id not in finished:
            finished[goal_id] = {
                "outcome": str(outcome),
                "budget_seconds": round(budget, 2),
                "elapsed_seconds": round(elapsed, 2),
                "remaining_seconds": round(remaining, 2),
                "finished_at": self._now().isoformat(),
            }
            if remaining > 0:
                self.state["redistributed_seconds"] = round(
                    float(self.state.get("redistributed_seconds", 0.0)) + remaining, 2
                )
        self._redistribute_to_unstarted()
        return {
            "goal_id": goal_id,
            "outcome": str(outcome),
            "budget_seconds": round(budget, 2),
            "elapsed_seconds": round(elapsed, 2),
            "remaining_seconds": round(remaining, 2),
        }

    def _redistribute_to_unstarted(self) -> None:
        finished_ids = set(self.state["finished_goals"])
        started_ids = set(self.state["started_goals"])
        candidates = [s for s in self._goal_states() if self._goal_id(s) not in finished_ids and self._goal_id(s) not in started_ids]
        if not candidates:
            return
        # The global wall-clock remainder is authoritative. This prevents
        # allocation drift after answer/evaluation/generation overhead.
        remaining = self.global_remaining()
        allocations = self._allocate(remaining, candidates)
        for state in candidates:
            gid = self._goal_id(state)
            self.state["allocations"][gid] = allocations.get(gid, 0.0)

    def snapshot(self, current_goal_id: str | None = None) -> dict[str, Any]:
        current = str(current_goal_id).strip() if current_goal_id else None
        goals = {}
        for state in self._goal_states():
            gid = self._goal_id(state)
            finished = self.state["finished_goals"].get(gid)
            goals[gid] = {
                "budget_seconds": round(self.goal_budget(gid), 2),
                "elapsed_seconds": round(self.goal_elapsed(gid), 2),
                "remaining_seconds": round(self.goal_remaining(gid), 2),
                "status": "completed" if getattr(state, "completed", False) else ("failed" if getattr(state, "failed", False) else "running" if gid == current else "pending"),
                "outcome": finished.get("outcome") if finished else None,
                "finished_remaining_seconds": finished.get("remaining_seconds") if finished else None,
            }
        return {
            "version": self.VERSION,
            "total_duration_seconds": round(self._duration(), 2),
            "allocation_mode": self.state.get("allocation_mode", "auto"),
            "global_elapsed_seconds": round(self._elapsed(), 2),
            "global_remaining_seconds": round(self.global_remaining(), 2),
            "current_goal_id": current,
            "goals": goals,
            "redistributed_seconds": round(float(self.state.get("redistributed_seconds", 0.0)), 2),
        }
