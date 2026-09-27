"""
app/assessment/result_builder.py

Builds an AssessmentResult from an InterviewSession.

Responsibilities
----------------
- Project already-calculated assessment state into AssessmentResult.
- Count evidence structurally.
- Project interview timeline events.
- Preserve canonical values produced by the assessment layer.

Non-responsibilities
--------------------
- Evaluating learner answers.
- Calculating mastery.
- Calculating confidence.
- Calculating achievement levels.
- Deciding whether an indicator is demonstrated.
- Deciding whether a goal is complete.
- Computing research metrics.
- Selecting goals or indicators.
- Performing interview navigation.

Canonical ownership
-------------------
IndicatorState is the source of truth for indicator assessment values:

    IndicatorState.achievement_level
    IndicatorState.confidence
    IndicatorState.demonstrated
    IndicatorState.attempts
    IndicatorState.feedback

GoalState is the source of truth for goal-level assessment values:

    GoalState.completed
    GoalState.coverage()
    GoalState.mastery()
    GoalState.confidence()

AssessmentResultBuilder only transfers those values into the
result model.

Research metrics are calculated later by MetricsService.
"""

from __future__ import annotations

from typing import Any

from .assessment_integrity import AssessmentIntegrity
from .fairness_calibrator import FairnessCalibrator
from .rubric_calibrator import RubricCalibration
from .abet_traceability import ABETTraceability
from .coverage_engine import CoverageEngine
from .scoring_normalizer import ScoringNormalizer
from .result import (
    AssessmentResult,
    GoalResult,
    IndicatorResult,
    InterviewEvent,
)


class AssessmentResultBuilder:
    """
    Convert an InterviewSession into an AssessmentResult.

    This class is a projection layer only.

    It does not perform assessment reasoning.
    """

    # ==========================================================
    # Public API
    # ==========================================================

    def build(
        self,
        session: Any,
    ) -> AssessmentResult:
        """
        Build the canonical assessment result for a session.

        Assessment values are read from GoalState and
        IndicatorState. They are not recalculated here.
        """

        # Refresh goal-specific timing before projecting the result.
        from .goal_time_manager import GoalTimeManager
        GoalTimeManager(session).snapshot(getattr(session, "current_goal_id", None))

        result = AssessmentResult(
            session_id=session.id,
            student_id=session.student_id,
            interviewer_id=getattr(
                session,
                "interviewer_id",
                None,
            ),
            configuration=getattr(
                session,
                "configuration",
                None,
            ),
            started_at=getattr(
                session,
                "started_at",
                None,
            ),
            finished_at=getattr(
                session,
                "finished_at",
                None,
            ),
            completed=bool(
                getattr(
                    session,
                    "completed",
                    False,
                )
            ),
        )

        self._build_goals(
            session=session,
            result=result,
        )

        self._build_timeline(
            session=session,
            result=result,
        )

        # v9.9: additive procedural fairness/scoring calibration diagnostics.
        # Diagnostic-only: never feeds back into assessment decisions.
        result.metadata["fairness_calibration"] = self._build_fairness_calibration(session)

        # v10.0: additive evidence-to-rubric calibration.
        # Diagnostic-only: never changes scores, completion, or navigation.
        result.metadata["rubric_calibration"] = self._build_rubric_calibration(session)

        # v10.1: additive ABET outcome/evidence traceability.
        # Safe reporting projection; learner answers/questions are excluded.
        result.metadata["abet_traceability"] = ABETTraceability.build(session)

        # v12.6.3: preserve a presentation-safe conversation snapshot for
        # authorized reports. This is reporting data only and does not feed
        # assessment decisions. The integrity manifest below deliberately
        # continues to exclude learner answer/question text.
        result.metadata["conversation"] = self._build_conversation_snapshot(session)

        # v10.2: create a tamper-evident, additive integrity manifest.
        # The manifest deliberately excludes learner answer/question text.
        evidence_records = []
        for goal_state in getattr(session, "goal_states", {}).values():
            evidence_records.extend(getattr(goal_state, "evidence", []) or [])
        result.metadata["assessment_integrity"] = AssessmentIntegrity.build_manifest(
            result=result,
            evidence_records=evidence_records,
        )

        return result

    # ==========================================================
    # v9.9 / v10.0 calibration projections
    # ==========================================================

    def _build_conversation_snapshot(self, session: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for turn in list(getattr(session, "turns", []) or []):
            metadata = getattr(turn, "metadata", {}) or {}
            assessment = metadata.get("assessment", {}) if isinstance(metadata, dict) else {}
            if not isinstance(assessment, dict):
                assessment = {}
            trace = metadata.get("adaptive_decision_trace") if isinstance(metadata, dict) else None
            continuity = metadata.get("question_continuity") if isinstance(metadata, dict) else None
            rows.append({
                "turn_number": int(getattr(turn, "index", getattr(turn, "number", 0)) or 0),
                "question": str(getattr(turn, "question", "") or ""),
                "answer": getattr(turn, "answer", None),
                "goal_id": getattr(turn, "goal_id", None),
                "indicator_id": getattr(turn, "indicator_id", None),
                "timestamp": getattr(turn, "timestamp", None),
                "evaluation": {
                    "achievement_level": assessment.get("achievement_level"),
                    "confidence": assessment.get("confidence"),
                    "evidence_strength": assessment.get("evidence_strength"),
                    "demonstrated": assessment.get("indicator_demonstrated", assessment.get("demonstrated")),
                    "bloom_level": assessment.get("bloom_level"),
                    "missing_elements": list(assessment.get("missing_elements", []) or []),
                    "feedback": assessment.get("feedback"),
                    "rationale": assessment.get("rationale"),
                    "mastery": assessment.get("mastery"),
                    "coverage": assessment.get("coverage"),
                    "difficulty_before": assessment.get("difficulty_before"),
                    "difficulty_after": assessment.get("difficulty_after"),
                    "difficulty_direction": assessment.get("difficulty_direction"),
                },
                "adaptive_decision_trace": trace,
                "question_continuity": continuity,
            })
        return rows

    def _build_fairness_calibration(self, session: Any) -> dict[str, Any]:
        """Build procedural fairness diagnostics without mutating assessment state."""
        goal_states = getattr(session, "goal_states", None) or {}
        goals = {}
        for goal_id, goal_state in goal_states.items():
            goals[str(goal_id)] = FairnessCalibrator.calibrate_goal(goal_state)
        return {
            "calibration_version": FairnessCalibrator.VERSION,
            "diagnostic_only": True,
            "protected_group_analysis": False,
            "goals": goals,
        }

    def _build_rubric_calibration(self, session: Any) -> dict[str, Any]:
        """Build a safe, additive evidence-to-rubric reliability report."""
        rows = []
        goal_states = getattr(session, "goal_states", None) or {}
        for goal_state in goal_states.values():
            calibration = RubricCalibration.build(goal_state)
            rows.append({
                "goal_id": str(getattr(goal_state, "goal_id", "") or getattr(getattr(goal_state, "goal", None), "id", "")),
                **calibration.to_dict(),
            })
        return {
            "version": RubricCalibration.VERSION,
            "goals": rows,
        }

    # ==========================================================
    # Goals
    # ==========================================================

    def _build_goals(
        self,
        session: Any,
        result: AssessmentResult,
    ) -> None:
        """
        Project GoalState objects into GoalResult objects.

        GoalState remains the source of truth for all goal-level
        assessment values.
        """

        goal_states = getattr(
            session,
            "goal_states",
            None,
        )

        if not goal_states:
            return

        for goal_state in goal_states.values():

            goal = getattr(
                goal_state,
                "goal",
                None,
            )

            if goal is None:
                continue

            goal_id = getattr(
                goal,
                "id",
                None,
            )

            if goal_id is None:
                continue

            snapshot = CoverageEngine().snapshot(goal_state)
            goal_result = GoalResult(
                goal_id=str(goal_id),

                title=self._resolve_goal_title(
                    goal
                ),

                completed=bool(
                    getattr(goal_state, "completed", False)
                    or snapshot.completed
                ),

                coverage=float(snapshot.coverage),

                mastery=float(snapshot.mastery),

                confidence=float(snapshot.confidence),

                time_budget_seconds=float(getattr(goal_state, "time_budget_seconds", 0.0) or 0.0),
                time_elapsed_seconds=float(getattr(goal_state, "time_elapsed_seconds", 0.0) or 0.0),
                time_remaining_seconds=float(getattr(goal_state, "time_remaining_seconds", 0.0) or 0.0),
                time_outcome=getattr(goal_state, "time_outcome", None),
            )

            self._build_indicators(
                goal_state=goal_state,
                goal_result=goal_result,
            )

            result.goals.append(
                goal_result
            )

    # ==========================================================
    # Goal Metadata
    # ==========================================================

    def _resolve_goal_title(
        self,
        goal: Any,
    ) -> str:
        """
        Resolve the human-readable goal title.

        Preferred order:

            goal.title
            goal.name
            goal.id
        """

        title = getattr(
            goal,
            "title",
            None,
        )

        if title:
            return str(title)

        name = getattr(
            goal,
            "name",
            None,
        )

        if name:
            return str(name)

        goal_id = getattr(
            goal,
            "id",
            "",
        )

        return str(goal_id)

    # ==========================================================
    # Indicators
    # ==========================================================

    def _build_indicators(
        self,
        goal_state: Any,
        goal_result: GoalResult,
    ) -> None:
        """
        Project IndicatorState objects into IndicatorResult objects.

        Indicator assessment values are projected from the canonical v9.7
        ScoringNormalizer evidence snapshot, with the existing IndicatorState
        used as the safe fallback when historical evidence is unavailable.
        """

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if not indicators:
            return

        for indicator_state in indicators.values():

            indicator_id = getattr(
                indicator_state,
                "id",
                None,
            )

            if indicator_id is None:
                continue

            normalized_mastery, normalized_confidence, normalized_strength = (
                ScoringNormalizer.indicator_snapshot(
                    goal_state,
                    indicator_state,
                )
            )

            indicator_result = IndicatorResult(
                indicator_id=str(
                    indicator_id
                ),

                description=str(
                    getattr(
                        indicator_state,
                        "description",
                        "",
                    )
                    or ""
                ),

                bloom_level=self._read_bloom_level(
                    indicator_state
                ),

                required=bool(
                    getattr(
                        indicator_state,
                        "required",
                        False,
                    )
                ),

                demonstrated=bool(
                    getattr(
                        indicator_state,
                        "demonstrated",
                        False,
                    )
                ),

                # v9.7 canonical final scoring: repeated evidence is
                # order-independent and must not regress to the latest
                # IndicatorState values merely because this is a report.
                mastery=normalized_mastery,

                confidence=normalized_confidence,

                attempts=self._read_integer_value(
                    indicator_state,
                    "attempts",
                ),

                evidence_count=self._count_indicator_evidence(
                    goal_state=goal_state,
                    indicator_id=indicator_id,
                ),

                feedback=self._read_feedback(
                    indicator_state
                ),
                evidence_strength=normalized_strength,
                missing_elements=list(getattr(indicator_state, "missing_elements", []) or []),
                difficulty=(
                    float(getattr(indicator_state, "difficulty", 0.0))
                    if getattr(indicator_state, "difficulty", None) is not None
                    else None
                ),
            )

            goal_result.indicators.append(
                indicator_result
            )

    # ==========================================================
    # Indicator Metadata
    # ==========================================================

    def _read_bloom_level(
        self,
        indicator_state: Any,
    ) -> str:
        """
        Read the indicator Bloom level.

        The result model expects a string.
        """

        value = getattr(
            indicator_state,
            "bloom_level",
            None,
        )

        if value is None:
            return ""

        return str(value)

    def _read_feedback(
        self,
        indicator_state: Any,
    ) -> str | None:
        """
        Read indicator feedback without modifying it.
        """

        value = getattr(
            indicator_state,
            "feedback",
            None,
        )

        if value is None:
            return None

        value = str(value).strip()

        return value or None

    # ==========================================================
    # Evidence
    # ==========================================================

    def _count_indicator_evidence(
        self,
        goal_state: Any,
        indicator_id: Any,
    ) -> int:
        """
        Count evidence records associated with an indicator.

        This is structural aggregation only.

        It does NOT calculate:

        - mastery
        - confidence
        - achievement level
        - demonstration
        - goal completion
        """

        evidence = getattr(
            goal_state,
            "evidence",
            None,
        )

        if not evidence:
            return 0

        return sum(
            1
            for item in evidence
            if getattr(
                item,
                "indicator_id",
                None,
            ) == indicator_id
        )

    # ==========================================================
    # Goal Metrics
    # ==========================================================

    def _read_goal_metric(
        self,
        goal_state: Any,
        name: str,
    ) -> float:
        """
        Read an already-calculated GoalState metric.

        Supports both:

            goal_state.mastery

        and:

            goal_state.mastery()

        The builder never calculates the metric itself.
        """

        value = getattr(
            goal_state,
            name,
            None,
        )

        if callable(value):
            value = value()

        if value is None:
            return 0.0

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # ==========================================================
    # Numeric State Values
    # ==========================================================

    def _read_numeric_value(
        self,
        state: Any,
        name: str,
    ) -> float:
        """
        Read an already-calculated numeric value from domain state.

        No scoring, normalization, clamping, or recalculation occurs.
        """

        value = getattr(
            state,
            name,
            0.0,
        )

        if value is None:
            return 0.0

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _read_integer_value(
        self,
        state: Any,
        name: str,
    ) -> int:
        """
        Read an already-calculated integer value from domain state.
        """

        value = getattr(
            state,
            name,
            0,
        )

        if value is None:
            return 0

        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # ==========================================================
    # Timeline
    # ==========================================================

    def _build_timeline(
        self,
        session: Any,
        result: AssessmentResult,
    ) -> None:
        """
        Project session events into the result timeline.

        Timeline conversion is structural projection only.
        """

        events = getattr(
            session,
            "events",
            None,
        )

        if not events:
            return

        for event in events:

            timestamp = getattr(
                event,
                "timestamp",
                None,
            )

            event_type = getattr(
                event,
                "event_type",
                None,
            )

            if timestamp is None or event_type is None:
                continue

            details = getattr(
                event,
                "details",
                None,
            )

            if details is None:
                details = {}

            if isinstance(details, dict):
                details = dict(details)

            result.timeline.append(
                InterviewEvent(
                    timestamp=timestamp,

                    event_type=str(
                        event_type
                    ),

                    goal_id=self._optional_string(
                        getattr(
                            event,
                            "goal_id",
                            None,
                        )
                    ),

                    indicator_id=self._optional_string(
                        getattr(
                            event,
                            "indicator_id",
                            None,
                        )
                    ),

                    details=details,
                )
            )

    # ==========================================================
    # Small Helpers
    # ==========================================================

    def _optional_string(
        self,
        value: Any,
    ) -> str | None:
        """
        Convert an optional identifier to a string.

        None remains None.
        """

        if value is None:
            return None

        return str(value)
