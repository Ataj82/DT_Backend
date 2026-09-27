"""
app/reports/metrics_service.py

Computes quantitative metrics from an AssessmentResult.

The MetricsService performs no repository access and no report
generation. It simply converts an AssessmentResult into a Metrics
object that can later be consumed by ReportService and
ResearchReportGenerator.
"""

from __future__ import annotations

from ..reports.models import (
    Metrics,
    GoalMetric,
    IndicatorMetric,
)


class MetricsService:
    """
    Computes assessment metrics from an AssessmentResult.
    """

    def compute(
        self,
        assessment_result,
    ) -> Metrics:
        """Compute metrics using explicit equal-weight goal aggregation.

        Each goal contributes one equally weighted observation to overall
        mastery, coverage, and confidence. Indicator-level values continue to
        come from the existing canonical assessment pipeline; this documents
        the policy without changing its behavior.
        """

        goal_metrics: list[GoalMetric] = []

        indicator_metrics: list[IndicatorMetric] = []

        total_mastery = 0.0
        total_coverage = 0.0
        total_confidence = 0.0

        completed_goals = 0

        total_questions = 0

        # ---------------------------------------------------------
        # Goals
        # ---------------------------------------------------------

        for goal in assessment_result.goals:

            goal_metrics.append(

                GoalMetric(

                    goal_id=goal.goal_id,

                    title=goal.title,

                    score=goal.mastery,

                    coverage=goal.coverage,

                    completed=goal.completed,
                    mastery=goal.mastery,
                    confidence=goal.confidence,

                    time_budget_seconds=goal.time_budget_seconds,
                    time_elapsed_seconds=goal.time_elapsed_seconds,
                    time_remaining_seconds=goal.time_remaining_seconds,
                    time_outcome=goal.time_outcome,

                )

            )

            total_mastery += goal.mastery

            total_coverage += goal.coverage
            total_confidence += goal.confidence

            if goal.completed:
                completed_goals += 1

            # -----------------------------------------------------
            # Indicators
            # -----------------------------------------------------

            for indicator in goal.indicators:

                indicator_metrics.append(

                    IndicatorMetric(

                        indicator_id=indicator.indicator_id,

                        description=indicator.description,

                        achieved_level=indicator.mastery,
                        achievement_level=indicator.mastery * 6.0,
                        mastery=indicator.mastery,
                        confidence=indicator.confidence,
                        evidence_strength=indicator.evidence_strength,
                        bloom_level=indicator.bloom_level,
                        required=indicator.required,
                        feedback=indicator.feedback,
                        attempts=indicator.attempts,
                        demonstrated=indicator.demonstrated,

                    )

                )

                total_questions += indicator.attempts

        # ---------------------------------------------------------
        # Overall
        # ---------------------------------------------------------

        goal_count = len(goal_metrics)

        overall_score = (
            total_mastery / goal_count
            if goal_count
            else 0.0
        )

        overall_coverage = (
            total_coverage / goal_count
            if goal_count
            else 0.0
        )

        overall_confidence = (
            total_confidence / goal_count
            if goal_count
            else 0.0
        )

        completed = (
            completed_goals == goal_count
            if goal_count
            else False
        )

        return Metrics(

            overall_score=overall_score,

            overall_coverage=overall_coverage,

            overall_confidence=overall_confidence,

            completed=completed,

            total_questions=total_questions,

            goal_metrics=goal_metrics,

            indicator_metrics=indicator_metrics,

        )