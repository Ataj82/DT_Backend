"""Adaptive difficulty control for interview questions.

The controller converts the latest structured answer evidence into a
bounded difficulty target for the next question. It is deterministic,
stateless, and mutates only the supplied IndicatorState through one
explicit update method.

Difficulty is intentionally separate from Bloom level: Bloom describes
cognitive operation; difficulty describes challenge/complexity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DifficultyDecision:
    previous_difficulty: float
    new_difficulty: float
    performance: float
    direction: str
    reason: str


class AdaptiveDifficultyController:
    """Deterministic controller for per-indicator difficulty."""

    DEFAULT_MIN = 0.20
    DEFAULT_MAX = 0.95
    DEFAULT_STEP = 0.10
    DEFAULT_HIGH = 0.78
    DEFAULT_LOW = 0.45
    DEFAULT_SMOOTHING = 0.60

    def __init__(
        self,
        *,
        minimum: float = DEFAULT_MIN,
        maximum: float = DEFAULT_MAX,
        step: float = DEFAULT_STEP,
        high_threshold: float = DEFAULT_HIGH,
        low_threshold: float = DEFAULT_LOW,
        smoothing: float = DEFAULT_SMOOTHING,
        strong_streak: int = 1,
        weak_streak: int = 1,
    ) -> None:
        self.minimum = self._bounded(minimum)
        self.maximum = self._bounded(maximum)
        if self.maximum < self.minimum:
            raise ValueError("maximum difficulty must be >= minimum difficulty")
        self.step = max(0.01, min(1.0, float(step)))
        self.high_threshold = self._bounded(high_threshold)
        self.low_threshold = self._bounded(low_threshold)
        if self.low_threshold >= self.high_threshold:
            raise ValueError("low_threshold must be < high_threshold")
        self.smoothing = max(0.0, min(1.0, float(smoothing)))
        self.strong_streak = max(1, int(strong_streak))
        self.weak_streak = max(1, int(weak_streak))

    def initial_difficulty(self, *, goal: Any, indicator: Any) -> float:
        """Resolve a safe starting difficulty from indicator, then goal."""
        candidates = (
            getattr(indicator, "difficulty", None),
            getattr(indicator, "initial_difficulty", None),
            getattr(goal, "difficulty", None),
            0.5,
        )
        for value in candidates:
            try:
                if value is not None:
                    return self._clamp(float(value))
            except (TypeError, ValueError):
                continue
        return 0.5

    def target_difficulty(self, *, goal: Any, indicator: Any) -> float:
        """Return the already-adapted target, initializing it safely if needed."""
        current = getattr(indicator, "difficulty", None)
        if current is None:
            current = self.initial_difficulty(goal=goal, indicator=indicator)
            setattr(indicator, "difficulty", current)
            if hasattr(indicator, "difficulty_history") and not indicator.difficulty_history:
                indicator.difficulty_history.append(current)
        return self._clamp(float(current))

    def performance(self, evidence: Any) -> float:
        """Convert structured evaluation evidence into [0,1] performance."""
        achievement = self._achievement(evidence)
        confidence = self._probability(getattr(evidence, "confidence", 0.0))
        evidence_strength = self._probability(getattr(evidence, "evidence_strength", 0.0))
        demonstrated = bool(getattr(evidence, "indicator_demonstrated", False))

        # Achievement is authoritative. Confidence/evidence quality make
        # the controller conservative when the LLM is uncertain.
        score = (
            0.70 * achievement
            + 0.15 * confidence
            + 0.15 * evidence_strength
        )
        if demonstrated:
            score = min(1.0, score + 0.05)
        return max(0.0, min(1.0, score))

    def update(self, *, indicator: Any, evidence: Any) -> DifficultyDecision:
        """Update the next-question difficulty for one indicator."""
        previous = self._clamp(getattr(indicator, "difficulty", 0.5))
        performance = self.performance(evidence)
        history = list(getattr(indicator, "difficulty_history", []) or [])

        performance_history = list(
            getattr(indicator, "difficulty_performance_history", []) or []
        )
        performance_history.append(round(performance, 4))
        if len(performance_history) > 10:
            performance_history = performance_history[-10:]
        if hasattr(indicator, "difficulty_performance_history"):
            indicator.difficulty_performance_history = performance_history

        strong_count = self._consecutive(
            performance_history, lambda value: value >= self.high_threshold
        )
        weak_count = self._consecutive(
            performance_history, lambda value: value <= self.low_threshold
        )
        strong = strong_count >= self.strong_streak
        weak = weak_count >= self.weak_streak

        if strong:
            new = self._clamp(previous + self.step)
            direction = "increase" if new > previous else "hold"
            reason = (
                f"strong performance ({performance:.2f}, streak={strong_count}) "
                "-> increase challenge"
            )
        elif weak:
            new = self._clamp(previous - self.step)
            direction = "decrease" if new < previous else "hold"
            reason = (
                f"weak performance ({performance:.2f}, streak={weak_count}) "
                "-> reduce challenge"
            )
        else:
            # Smooth toward the current target only when the evidence is
            # between the strong/weak bands. This prevents oscillation.
            target = self._clamp(performance)
            new = self._clamp(
                previous + self.smoothing * self.step * (target - previous)
            )
            if abs(new - previous) < 0.01:
                new = previous
            direction = "hold" if new == previous else ("increase" if new > previous else "decrease")
            reason = f"moderate performance ({performance:.2f}) -> stabilize difficulty"

        # Avoid accumulating duplicate values and cap history.
        history.append(round(new, 4))
        if len(history) > 10:
            history = history[-10:]

        setattr(indicator, "difficulty", new)
        if hasattr(indicator, "difficulty_history"):
            indicator.difficulty_history = history
        if hasattr(indicator, "last_difficulty_reason"):
            indicator.last_difficulty_reason = reason

        return DifficultyDecision(
            previous_difficulty=previous,
            new_difficulty=new,
            performance=performance,
            direction=direction,
            reason=reason,
        )

    @staticmethod
    def _consecutive(history: list[float], predicate) -> int:
        count = 0
        for value in reversed(history):
            if not predicate(value):
                break
            count += 1
        return count

    @staticmethod
    def _achievement(evidence: Any) -> float:
        value = getattr(evidence, "achievement_level", None)
        try:
            level = int(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, (level - 1) / 5.0))

    @staticmethod
    def _probability(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def _clamp(self, value: float) -> float:
        return max(self.minimum, min(self.maximum, float(value)))

    @staticmethod
    def _bounded(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError("difficulty thresholds must be numeric") from exc
