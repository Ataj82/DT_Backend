"""
app/api/mappers/interview_mapper.py

Presentation mapper for interview API responses.

Architecture
------------

InterviewSession
    |
    +-- GoalState
    |     |
    |     +-- IndicatorState
    |
    +-- ConversationTurn
    |
    +-- AssessmentResult
    |
    v
InterviewMapper
    |
    v
API DTOs

Ownership
---------

The assessment layer owns:

- achievement_level
- score semantics
- mastery
- confidence
- evidence_strength
- demonstrated
- attempts
- completion
- passed
- assessment decisions

This mapper does NOT calculate those values.

It only projects canonical domain state into API DTOs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from datetime import datetime, timezone

from ...api.schemas.common import InterviewStatus
from ...assessment.coverage_engine import CoverageEngine

from ...api.schemas.interviews import (
    AnswerEvaluation,
    AssessmentResultResponse,
    ConversationTurnResponse,
    QuestionResponse,
    GoalProgressResponse,
    IndicatorProgressResponse,
    InterviewSessionResponse,
)


class InterviewMapper:
    """
    Convert interview domain objects into API response DTOs.

    This class contains no assessment, navigation, or progression
    algorithms.
    """

    # ==========================================================
    # Session
    # ==========================================================

    @classmethod
    def to_session(
        cls,
        session,
        *,
        result: Any | None = None,
    ) -> InterviewSessionResponse:
        """
        Convert an InterviewSession into an API response.
        """

        if session is None:
            raise ValueError(
                "InterviewMapper.to_session() requires a session."
            )

        completed = bool(
            getattr(
                session,
                "completed",
                False,
            )
        )

        status = (
            InterviewStatus.COMPLETED
            if completed
            else InterviewStatus.RUNNING
        )

        last_turn = getattr(
            session,
            "last_turn",
            None,
        )

        current_question = None

        if last_turn is not None and not completed:
            current_question = getattr(
                last_turn,
                "question",
                None,
            )

        current_goal = cls._current_goal_name(
            session
        )

        knowledge_model = getattr(
            session,
            "knowledge_model",
            None,
        )

        goal_model = getattr(
            session,
            "goal_model",
            None,
        )

        goal_states = getattr(
            session,
            "goal_states",
            {},
        )

        if isinstance(
            goal_states,
            Mapping,
        ):
            goal_state_values = goal_states.values()
        else:
            goal_state_values = ()

        turns = getattr(
            session,
            "turns",
            (),
        )

        # v12.6.3: expose a live timing snapshot on every session GET so
        # the clean student UI can recover timers after refresh/reconnect.
        from ...assessment.goal_time_manager import GoalTimeManager
        snapshot = GoalTimeManager(session).snapshot(getattr(session, "current_goal_id", None))
        configuration = getattr(session, "configuration", None)
        duration_value = getattr(configuration, "duration_seconds", None)
        if duration_value is None:
            duration_value = float(getattr(configuration, "max_minutes", 30) or 30) * 60.0
        started_at = getattr(session, "started_at", None)
        if started_at is not None:
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
        else:
            elapsed_seconds = 0.0
        remaining_seconds = max(0.0, float(duration_value) - elapsed_seconds)
        current_goal_id = getattr(session, "current_goal_id", None)
        current_goal_timing = (snapshot.get("goals", {}) or {}).get(str(current_goal_id), {})

        return InterviewSessionResponse(
            session_id=getattr(
                session,
                "id",
                "",
            ),
            student_id=getattr(
                session,
                "student_id",
                "",
            ),
            knowledge_id=getattr(
                knowledge_model,
                "id",
                "",
            ),
            goal_model_id=getattr(
                goal_model,
                "id",
                "",
            ),
            status=status,
            created_at=getattr(
                session,
                "started_at",
                None,
            ),
            current_question=current_question,
            current_goal=current_goal,
            duration_seconds=int(float(duration_value)),
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=remaining_seconds,
            current_goal_id=current_goal_id,
            current_goal_budget_seconds=current_goal_timing.get("budget_seconds"),
            current_goal_elapsed_seconds=current_goal_timing.get("elapsed_seconds"),
            current_goal_remaining_seconds=current_goal_timing.get("remaining_seconds"),
            goal_time_snapshot=snapshot,
            **cls._live_metrics(session),
            progress=[
                cls.to_goal_progress(
                    goal_state,
                    timing=(snapshot.get("goals", {}) or {}).get(
                        str(getattr(goal_state, "goal_id", None) or getattr(getattr(goal_state, "goal", None), "id", "")),
                        {},
                    ),
                )
                for goal_state in goal_state_values
            ],
            conversation=[
                cls.to_turn(
                    turn,
                    session=session,
                )
                for turn in turns
            ],
            result=(
                cls.to_result(result)
                if result is not None
                else None
            ),
            configuration=getattr(
                session,
                "configuration",
                None,
            ),
            metadata=getattr(
                session,
                "metadata",
                {},
            ),
        )

    @classmethod
    def _live_metrics(cls, session) -> dict[str, Any]:
        """Project authoritative live assessment metrics without mutating state."""
        goal_states = getattr(session, "goal_states", {}) or {}
        states = list(goal_states.values()) if isinstance(goal_states, Mapping) else []
        snapshots = [CoverageEngine().snapshot(state) for state in states]
        total_goals = len(states)
        completed_goals = sum(1 for state, snap in zip(states, snapshots) if bool(getattr(state, "completed", False) or snap.completed))
        overall_mastery = sum(s.mastery for s in snapshots) / total_goals if total_goals else 0.0
        overall_coverage = sum(s.coverage for s in snapshots) / total_goals if total_goals else 0.0
        overall_confidence = sum(s.confidence for s in snapshots) / total_goals if total_goals else 0.0
        total_indicators = sum(len(getattr(state, "indicators", {}) or {}) for state in states)
        assessed_indicators = sum(
            1 for state in states for indicator in (getattr(state, "indicators", {}) or {}).values()
            if getattr(indicator, "achievement_level", None) is not None
        )
        turns = list(getattr(session, "turns", ()) or ())
        current_indicator_id = None
        current_bloom_level = None
        current_difficulty = None
        current_goal_id = getattr(session, "current_goal_id", None)
        if current_goal_id is not None:
            state = goal_states.get(current_goal_id) if isinstance(goal_states, Mapping) else None
            if state is not None:
                current_indicator_id = getattr(state, "current_indicator_id", None)
                indicators = getattr(state, "indicators", {}) or {}
                indicator = indicators.get(current_indicator_id) if current_indicator_id is not None else None
                if indicator is not None:
                    current_bloom_level = str(getattr(indicator, "bloom_level", "") or "") or None
                    value = getattr(indicator, "difficulty", None)
                    current_difficulty = float(value) if value is not None else None
        return {
            "overall_mastery": float(overall_mastery),
            "overall_coverage": float(overall_coverage),
            "overall_confidence": float(overall_confidence),
            "completed_goals": completed_goals,
            "total_goals": total_goals,
            "questions_asked": len(turns),
            "assessed_indicators": assessed_indicators,
            "total_indicators": total_indicators,
            "current_indicator_id": current_indicator_id,
            "current_bloom_level": current_bloom_level,
            "current_difficulty": current_difficulty,
        }

    # ==========================================================
    # Current Goal
    # ==========================================================

    @classmethod
    def _current_goal_name(
        cls,
        session,
    ) -> str | None:
        """
        Return the display name of the currently active goal.

        This method only reads domain state.
        """

        current_goal_id = getattr(
            session,
            "current_goal_id",
            None,
        )

        if current_goal_id is None:
            return None

        get_goal_state = getattr(
            session,
            "get_goal_state",
            None,
        )

        if not callable(
            get_goal_state
        ):
            return None

        goal_state = get_goal_state(
            current_goal_id
        )

        if goal_state is None:
            return None

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        if goal is None:
            return None

        return (
            getattr(
                goal,
                "title",
                None,
            )
            or getattr(
                goal,
                "name",
                None,
            )
            or getattr(
                goal,
                "id",
                None,
            )
        )

    # ==========================================================
    # Conversation
    # ==========================================================

    @classmethod
    def to_turn(
        cls,
        turn,
        *,
        session=None,
    ) -> ConversationTurnResponse:
        """
        Convert one ConversationTurn into an API response.

        Assessment values are resolved from canonical
        IndicatorState whenever a session is supplied.
        """

        if turn is None:
            raise ValueError(
                "InterviewMapper.to_turn() requires a turn."
            )

        indicator_state = cls._indicator_state_for_turn(
            turn,
            session=session,
        )

        score = None
        achievement_level = None
        confidence = None
        evidence_strength = None
        demonstrated = None
        attempts = None
        difficulty_before = None
        difficulty_after = None
        difficulty_performance = None
        difficulty_direction = None
        feedback = None
        bloom_level = None
        missing_elements: list[str] = []
        rationale = None
        coverage = None
        mastery = None

        metadata = getattr(
            turn,
            "metadata",
            {},
        )
        if not isinstance(metadata, Mapping):
            metadata = {}

        assessment_metadata = metadata.get(
            "assessment",
            {},
        )

        if isinstance(assessment_metadata, Mapping):
            score = cls._number_or_none(assessment_metadata.get("score"))
            achievement_level = cls._number_or_none(assessment_metadata.get("achievement_level"))
            confidence = cls._number_or_none(assessment_metadata.get("confidence"))
            evidence_strength = cls._number_or_none(assessment_metadata.get("evidence_strength"))
            coverage = cls._number_or_none(assessment_metadata.get("coverage"))
            mastery = cls._number_or_none(assessment_metadata.get("mastery"))

            demonstrated_value = assessment_metadata.get("indicator_demonstrated")
            if demonstrated_value is None:
                demonstrated_value = assessment_metadata.get("demonstrated")
            if demonstrated_value is not None:
                demonstrated = bool(demonstrated_value)

            attempts_value = assessment_metadata.get("attempts")
            if attempts_value is not None:
                attempts = cls._int_or_none(attempts_value)

            difficulty_before = cls._number_or_none(assessment_metadata.get("difficulty_before"))
            difficulty_after = cls._number_or_none(assessment_metadata.get("difficulty_after"))
            difficulty_performance = cls._number_or_none(assessment_metadata.get("difficulty_performance"))
            if assessment_metadata.get("difficulty_direction") is not None:
                difficulty_direction = str(assessment_metadata.get("difficulty_direction"))

            bloom_value = assessment_metadata.get("bloom_level")
            if bloom_value is not None:
                bloom_level = str(bloom_value)

            missing_value = assessment_metadata.get("missing_elements")
            if isinstance(missing_value, (list, tuple)):
                missing_elements = [str(item) for item in missing_value]
            elif missing_value:
                missing_elements = [str(missing_value)]

            rationale_value = assessment_metadata.get("rationale")
            if rationale_value:
                rationale = str(rationale_value)

            feedback_value = assessment_metadata.get("feedback")
            if feedback_value:
                feedback = str(feedback_value)

        if indicator_state is not None:

            if achievement_level is None:
                achievement_level = cls._number_or_none(
                    getattr(indicator_state, "achievement_level", None)
                )

            # ConversationTurnResponse retains score as an API
            # compatibility field. It is populated only from an
            # already-produced domain score when available.
            if score is None:
                score = cls._number_or_none(
                    getattr(indicator_state, "score", None)
                )

            if confidence is None:
                confidence = cls._number_or_none(
                    getattr(indicator_state, "confidence", None)
                )

            if evidence_strength is None:
                evidence_strength = cls._number_or_none(
                    getattr(indicator_state, "evidence_strength", None)
                )

            if attempts is None:
                attempts = cls._int_or_none(
                    getattr(indicator_state, "attempts", None)
                )

            if demonstrated is None:
                demonstrated_value = getattr(
                    indicator_state,
                    "demonstrated",
                    None,
                )

                if demonstrated_value is not None:
                    demonstrated = bool(
                        demonstrated_value
                    )

            if not feedback:
                feedback_value = getattr(
                    indicator_state,
                    "feedback",
                    None,
                )

                if feedback_value:
                    feedback = str(
                        feedback_value
                    )

        # ------------------------------------------------------
        # Legacy / conversation feedback and old-turn compatibility
        # ------------------------------------------------------

        if not feedback:
            metadata_feedback = metadata.get("feedback")
            if metadata_feedback:
                feedback = str(metadata_feedback)

        if not feedback and isinstance(assessment_metadata, Mapping):
            metadata_assessment_feedback = assessment_metadata.get("feedback")
            if metadata_assessment_feedback:
                feedback = str(metadata_assessment_feedback)

        if not feedback:
            turn_feedback = getattr(turn, "feedback", None)
            if turn_feedback:
                feedback = str(turn_feedback)

        if indicator_state is None and isinstance(assessment_metadata, Mapping):
            if score is None:
                score = cls._number_or_none(assessment_metadata.get("score"))
            if achievement_level is None:
                achievement_level = cls._number_or_none(assessment_metadata.get("achievement_level"))
            if confidence is None:
                confidence = cls._number_or_none(assessment_metadata.get("confidence"))
            if evidence_strength is None:
                evidence_strength = cls._number_or_none(assessment_metadata.get("evidence_strength"))
            if coverage is None:
                coverage = cls._number_or_none(assessment_metadata.get("coverage"))
            if mastery is None:
                mastery = cls._number_or_none(assessment_metadata.get("mastery"))
            if demonstrated is None:
                demonstrated_value = assessment_metadata.get("indicator_demonstrated")
                if demonstrated_value is None:
                    demonstrated_value = assessment_metadata.get("demonstrated")
                if demonstrated_value is not None:
                    demonstrated = bool(demonstrated_value)
            if attempts is None:
                attempts = cls._int_or_none(assessment_metadata.get("attempts"))

            if bloom_level is None and assessment_metadata.get("bloom_level") is not None:
                bloom_level = str(assessment_metadata.get("bloom_level"))
            if not missing_elements:
                missing_value = assessment_metadata.get("missing_elements")
                if isinstance(missing_value, (list, tuple)):
                    missing_elements = [str(item) for item in missing_value]
                elif missing_value:
                    missing_elements = [str(missing_value)]
            if rationale is None and assessment_metadata.get("rationale"):
                rationale = str(assessment_metadata.get("rationale"))

        # ------------------------------------------------------
        # Assessment decision
        # ------------------------------------------------------

        decision = getattr(turn, "decision", None)
        decision_status = cls._decision_status(decision)

        if decision_status is None and isinstance(assessment_metadata, Mapping):
            decision_status = cls._normalize_status(assessment_metadata.get("status"))

        return ConversationTurnResponse(
            turn_number=getattr(
                turn,
                "index",
                0,
            ),
            question=getattr(
                turn,
                "question",
                "",
            ),
            answer=getattr(
                turn,
                "answer",
                None,
            ),
            feedback=feedback,
            timestamp=getattr(
                turn,
                "timestamp",
                None,
            ),
            goal_id=getattr(
                turn,
                "goal_id",
                None,
            ),
            indicator_id=getattr(
                turn,
                "indicator_id",
                None,
            ),
            score=score,
            achievement_level=achievement_level,
            confidence=confidence,
            evidence_strength=evidence_strength,
            bloom_level=bloom_level,
            missing_elements=missing_elements,
            rationale=rationale,
            coverage=coverage,
            mastery=mastery,
            demonstrated=demonstrated,
            attempts=attempts,
            difficulty_before=difficulty_before,
            difficulty_after=difficulty_after,
            difficulty_performance=difficulty_performance,
            difficulty_direction=difficulty_direction,
            status=decision_status,
        )

    # ==========================================================
    # Submit-answer transport
    # ==========================================================

    @classmethod
    def to_answer_evaluation(
        cls,
        turn,
        *,
        session=None,
    ) -> AnswerEvaluation:
        """
        Project the evaluation snapshot stored on the answered turn.

        The answered turn is intentionally used instead of the newly
        generated next turn because IndicatorState is mutable and may
        already have moved to another indicator.
        """
        mapped = cls.to_turn(turn, session=session)

        metadata = getattr(turn, "metadata", {}) or {}
        assessment = metadata.get("assessment", {}) if isinstance(metadata, Mapping) else {}
        if not isinstance(assessment, Mapping):
            assessment = {}

        covered = assessment.get("covered")
        if covered is None:
            covered = mapped.demonstrated

        return AnswerEvaluation(
            turn_index=int(getattr(turn, "index", 0)),
            question=str(getattr(turn, "question", "") or ""),
            answer=str(getattr(turn, "answer", "") or ""),
            score=mapped.score,
            achievement_level=mapped.achievement_level if mapped.achievement_level is not None else 1.0,
            confidence=mapped.confidence if mapped.confidence is not None else 0.0,
            evidence_strength=mapped.evidence_strength if mapped.evidence_strength is not None else 0.0,
            indicator_demonstrated=(
                mapped.demonstrated if mapped.demonstrated is not None else False
            ),
            demonstrated=mapped.demonstrated,
            bloom_level=mapped.bloom_level,
            missing_elements=mapped.missing_elements,
            feedback=mapped.feedback or "",
            rationale=mapped.rationale,
            covered=bool(covered),
            coverage=mapped.coverage,
            mastery=mapped.mastery,
            attempts=mapped.attempts,
            status=mapped.status,
            goal_id=mapped.goal_id,
            indicator_id=mapped.indicator_id,
            assessment_confidence=cls._number_or_none(
                assessment.get("assessment_confidence")
            ),
        )

    @classmethod
    def to_question(
        cls,
        turn,
        *,
        session=None,
    ) -> QuestionResponse | None:
        """Project a newly generated interview turn into QuestionResponse."""
        if turn is None or not getattr(turn, "question", None):
            return None

        indicator_id = getattr(turn, "indicator_id", None)
        goal_id = getattr(turn, "goal_id", None)
        if not goal_id or not indicator_id:
            return None

        indicator_state = cls._indicator_state_for_turn(turn, session=session)
        bloom_level = getattr(indicator_state, "bloom_level", "") or ""
        attempts = int(getattr(indicator_state, "attempts", 0) or 0)

        assessment_metadata = getattr(turn, "metadata", {}).get("assessment", {})
        if not isinstance(assessment_metadata, Mapping):
            assessment_metadata = {}

        return QuestionResponse(
            session_id=str(getattr(session, "id", "")),
            turn_index=int(getattr(turn, "index", 0)),
            question=str(turn.question),
            goal_id=str(goal_id),
            indicator_id=str(indicator_id),
            bloom_level=str(bloom_level),
            attempt=max(1, attempts + 1),
            is_followup=attempts > 0,
            difficulty=cls._number_or_none(assessment_metadata.get("difficulty")),
            difficulty_reason=(
                str(assessment_metadata.get("difficulty_reason"))
                if assessment_metadata.get("difficulty_reason")
                else None
            ),
        )

    # ==========================================================
    # Indicator State Resolution
    # ==========================================================

    @classmethod
    def _indicator_state_for_turn(
        cls,
        turn,
        *,
        session=None,
    ):
        """
        Resolve the canonical IndicatorState associated with
        a conversation turn.
        """

        if session is None:
            return None

        goal_id = getattr(
            turn,
            "goal_id",
            None,
        )

        indicator_id = getattr(
            turn,
            "indicator_id",
            None,
        )

        if (
            goal_id is None
            or indicator_id is None
        ):
            return None

        get_goal_state = getattr(
            session,
            "get_goal_state",
            None,
        )

        if not callable(
            get_goal_state
        ):
            return None

        goal_state = get_goal_state(
            goal_id
        )

        if goal_state is None:
            return None

        get_indicator = getattr(
            goal_state,
            "get_indicator",
            None,
        )

        if callable(
            get_indicator
        ):
            return get_indicator(
                indicator_id
            )

        indicators = getattr(
            goal_state,
            "indicators",
            None,
        )

        if isinstance(
            indicators,
            Mapping,
        ):
            return indicators.get(
                indicator_id
            )

        return None

    # ==========================================================
    # Decision
    # ==========================================================

    @staticmethod
    def _decision_status(
        decision,
    ) -> str | None:
        """
        Read status from the canonical GoalDecision.
        """

        if decision is None:
            return None

        status = getattr(
            decision,
            "status",
            None,
        )

        return InterviewMapper._normalize_status(
            status
        )

    @staticmethod
    def _normalize_status(
        status,
    ) -> str | None:
        """
        Normalize enum/string status for the API DTO.

        This only converts representation.
        """

        if status is None:
            return None

        value = getattr(
            status,
            "value",
            status,
        )

        if value is None:
            return None

        return str(
            value
        )

    # ==========================================================
    # Goal Progress
    # ==========================================================

    @classmethod
    def to_goal_progress(
        cls,
        goal_state,
        *,
        timing: Mapping[str, Any] | None = None,
    ) -> GoalProgressResponse:
        """
        Convert one GoalState into an API goal-progress response.
        """

        if goal_state is None:
            raise ValueError(
                "InterviewMapper.to_goal_progress() "
                "requires a goal_state."
            )

        goal = getattr(
            goal_state,
            "goal",
            None,
        )

        goal_id = getattr(
            goal,
            "id",
            "",
        )

        goal_name = (
            getattr(
                goal,
                "title",
                None,
            )
            or getattr(
                goal,
                "name",
                None,
            )
            or goal_id
            or "Unknown goal"
        )

        indicators = getattr(
            goal_state,
            "indicators",
            {},
        )

        if isinstance(
            indicators,
            Mapping,
        ):
            indicator_states = indicators.values()
        else:
            indicator_states = ()

        # CoverageEngine is the canonical owner of derived live assessment
        # metrics. The mapper only projects its read-only snapshot.
        snapshot = CoverageEngine().snapshot(goal_state)
        indicator_states = list(indicator_states)
        assessed_count = sum(1 for item in indicator_states if getattr(item, "achievement_level", None) is not None)

        return GoalProgressResponse(
            goal_id=goal_id,
            goal_name=goal_name,
            completed=bool(
                getattr(goal_state, "completed", False)
                or snapshot.completed
            ),
            coverage=float(snapshot.coverage),
            mastery=float(snapshot.mastery),
            confidence=float(snapshot.confidence),
            time_budget_seconds=float((timing or {}).get("budget_seconds", getattr(goal_state, "time_budget_seconds", 0.0)) or 0.0),
            time_elapsed_seconds=float((timing or {}).get("elapsed_seconds", getattr(goal_state, "time_elapsed_seconds", 0.0)) or 0.0),
            time_remaining_seconds=float((timing or {}).get("remaining_seconds", getattr(goal_state, "time_remaining_seconds", 0.0)) or 0.0),
            time_outcome=(timing or {}).get("outcome", getattr(goal_state, "time_outcome", None)),
            assessed_indicators=assessed_count,
            total_indicators=len(indicator_states),
            indicators=[
                cls.to_indicator_progress(
                    indicator_state
                )
                for indicator_state
                in indicator_states
            ],
        )

    # ==========================================================
    # Indicator Progress
    # ==========================================================

    @staticmethod
    def to_indicator_progress(
        indicator_state,
    ) -> IndicatorProgressResponse:
        """
        Convert IndicatorState into the canonical API
        IndicatorProgressResponse.

        No assessment values are calculated here.
        """

        if indicator_state is None:
            raise ValueError(
                "InterviewMapper.to_indicator_progress() "
                "requires an indicator_state."
            )

        indicator_id = getattr(
            indicator_state,
            "id",
            "",
        )

        indicator_definition = getattr(
            indicator_state,
            "indicator",
            None,
        )

        description = (
            getattr(
                indicator_state,
                "description",
                None,
            )
            or getattr(
                indicator_definition,
                "description",
                None,
            )
            or getattr(
                indicator_state,
                "name",
                None,
            )
            or getattr(
                indicator_definition,
                "name",
                None,
            )
            or indicator_id
            or "Unknown indicator"
        )

        bloom_level = (
            getattr(
                indicator_state,
                "bloom_level",
                None,
            )
            or getattr(
                indicator_definition,
                "bloom_level",
                None,
            )
            or ""
        )

        achievement_level = (
            InterviewMapper._number_or_none(
                getattr(
                    indicator_state,
                    "achievement_level",
                    None,
                )
            )
        )

        confidence = (
            InterviewMapper._number_or_none(
                getattr(
                    indicator_state,
                    "confidence",
                    None,
                )
            )
        )

        evidence_strength = (
            InterviewMapper._number_or_none(
                getattr(
                    indicator_state,
                    "evidence_strength",
                    None,
                )
            )
        )

        attempts = (
            InterviewMapper._int_or_none(
                getattr(
                    indicator_state,
                    "attempts",
                    0,
                )
            )
        )

        demonstrated_value = getattr(
            indicator_state,
            "demonstrated",
            False,
        )

        demonstrated = bool(
            demonstrated_value
        )

        feedback = (
            getattr(
                indicator_state,
                "feedback",
                None,
            )
            or ""
        )

        return IndicatorProgressResponse(
            id=str(
                indicator_id
            ),
            description=str(
                description
            ),
            bloom_level=str(
                bloom_level
            ),
            attempts=(
                attempts
                if attempts is not None
                else 0
            ),
            demonstrated=demonstrated,
            achievement_level=achievement_level,
            confidence=confidence,
            evidence_strength=evidence_strength,
            feedback=str(
                feedback
            ),
        )

    # ==========================================================
    # Goal Aggregates
    # ==========================================================

    @staticmethod
    def _goal_mastery(
        goal_state,
    ) -> float | None:
        """
        Read the canonical goal mastery value.

        No aggregate calculation is performed here.
        """

        mastery = getattr(
            goal_state,
            "mastery",
            None,
        )

        if callable(
            mastery
        ):
            value = mastery()

            if value is None:
                return None

            return float(value)

        if mastery is None:
            return None

        return float(
            mastery
        )

    @staticmethod
    def _goal_confidence(
        goal_state,
    ) -> float | None:
        """
        Read the canonical goal confidence value.

        No confidence calculation is performed here.
        """

        confidence = getattr(
            goal_state,
            "confidence",
            None,
        )

        if callable(
            confidence
        ):
            value = confidence()

            if value is None:
                return None

            return float(value)

        if confidence is None:
            return None

        return float(
            confidence
        )

    # ==========================================================
    # Result
    # ==========================================================

    @staticmethod
    def to_result(
        result,
    ) -> AssessmentResultResponse:
        """
        Convert the canonical AssessmentResult into an API response.

        ``passed`` must already be decided by the assessment/result
        layer.
        """

        if result is None:
            raise ValueError(
                "InterviewMapper.to_result() "
                "requires an assessment result."
            )

        overall_mastery = getattr(
            result,
            "overall_mastery",
            None,
        )

        passed = getattr(
            result,
            "passed",
            None,
        )

        if overall_mastery is None:
            raise ValueError(
                "AssessmentResult is missing "
                "'overall_mastery'."
            )

        if passed is None:
            raise ValueError(
                "AssessmentResult is missing "
                "'passed'."
            )

        summary = getattr(
            result,
            "summary",
            "",
        )

        recommendations = getattr(
            result,
            "recommendations",
            [],
        )

        if recommendations is None:
            recommendations = []

        return AssessmentResultResponse(
            overall_score=float(
                overall_mastery
            ),
            passed=bool(
                passed
            ),
            summary=str(
                summary or ""
            ),
            recommendations=list(
                recommendations
            ),
        )

    # ==========================================================
    # Collections
    # ==========================================================

    @classmethod
    def to_sessions(
        cls,
        sessions,
    ):
        """
        Convert multiple InterviewSession objects.
        """

        return [
            cls.to_session(
                session
            )
            for session
            in sessions
        ]

    @classmethod
    def to_turns(
        cls,
        turns,
        *,
        session=None,
    ):
        """
        Convert multiple ConversationTurn objects.
        """

        return [
            cls.to_turn(
                turn,
                session=session,
            )
            for turn
            in turns
        ]

    # ==========================================================
    # Scalar Helpers
    # ==========================================================

    @staticmethod
    def _number_or_none(
        value,
    ) -> float | None:
        """
        Convert an already-calculated numeric domain value into
        the API representation.
        """

        if value is None:
            return None

        return float(
            value
        )

    @staticmethod
    def _int_or_none(
        value,
    ) -> int | None:
        """
        Convert an already-calculated integer domain value into
        the API representation.
        """

        if value is None:
            return None

        return int(
            value
        )