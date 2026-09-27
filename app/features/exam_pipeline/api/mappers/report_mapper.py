"""
app/api/mappers/report_mapper.py

Maps report domain objects to API DTOs.
"""

from __future__ import annotations

from ...api.schemas.reports import (
    ReportResponse,
    MetricsResponse,
    GoalMetricResponse,
    IndicatorMetricResponse,
    RecommendationResponse,
)


class ReportMapper:
    """
    Converts reporting domain objects into API DTOs.
    """

    # =========================================================
    # Goal Metrics
    # =========================================================

    @staticmethod
    def to_goal_metric(
        metric,
    ) -> GoalMetricResponse:

        return GoalMetricResponse(

            goal_id=metric.goal_id,

            title=metric.title,

            score=metric.score,

            coverage=metric.coverage,

            completed=metric.completed,
            mastery=metric.mastery,
            confidence=metric.confidence,
            time_budget_seconds=metric.time_budget_seconds,
            time_elapsed_seconds=metric.time_elapsed_seconds,
            time_remaining_seconds=metric.time_remaining_seconds,
            time_outcome=metric.time_outcome,
        )

    # =========================================================
    # Indicator Metrics
    # =========================================================

    @staticmethod
    def to_indicator_metric(
        metric,
    ) -> IndicatorMetricResponse:

        return IndicatorMetricResponse(

            indicator_id=metric.indicator_id,

            description=metric.description,

            achieved_level=metric.achieved_level,

            confidence=metric.confidence,

            attempts=metric.attempts,

            demonstrated=metric.demonstrated,
            achievement_level=metric.achievement_level,
            mastery=metric.mastery,
            evidence_strength=metric.evidence_strength,
            bloom_level=metric.bloom_level,
            required=metric.required,
            feedback=metric.feedback,
        )

    # =========================================================
    # Metrics
    # =========================================================

    @classmethod
    def to_metrics(
        cls,
        metrics,
    ) -> MetricsResponse:

        return MetricsResponse(

            overall_score=metrics.overall_score,

            overall_coverage=metrics.overall_coverage,

            overall_confidence=metrics.overall_confidence,

            completed=metrics.completed,

            total_questions=metrics.total_questions,

            goal_metrics=[
                cls.to_goal_metric(goal)
                for goal in metrics.goal_metrics
            ],
            indicator_metrics=[
                cls.to_indicator_metric(indicator)
                for indicator in metrics.indicator_metrics
            ],
        )

    # =========================================================
    # Recommendation
    # =========================================================

    @staticmethod
    def to_recommendation(
        recommendation,
    ) -> RecommendationResponse:

        return RecommendationResponse(

            priority=recommendation.priority,

            category=recommendation.category,

            title=recommendation.title,

            description=recommendation.description,

            action=recommendation.action,
        )

    # =========================================================
    # Report
    # =========================================================

    @classmethod
    def to_report(
        cls,
        report,
    ) -> ReportResponse:

        return ReportResponse(

            session_id=report.session_id,

            student_id=report.student_id,

            generated_at=report.generated_at,

            metrics=cls.to_metrics(
                report.metrics
            ),

            recommendations=[

                cls.to_recommendation(r)

                for r
                in report.recommendations

            ],

            metadata=report.metadata,
        )