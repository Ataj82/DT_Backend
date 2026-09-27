"""
app/reports/research_report_generator.py

Generates a Report from an AssessmentResult.

This class performs lightweight report construction only.
Metrics are computed separately by MetricsService.
"""

from __future__ import annotations

from datetime import datetime

from ..assessment.result import AssessmentResult
from ..reports.models import Report
from ..reports.report_generator import ReportGenerator


class ResearchReportGenerator(ReportGenerator):
    """
    Builds a Report from an AssessmentResult.
    """

    def build(
        self,
        result: AssessmentResult,
        metrics,
    ) -> Report:
        """
        Build the final report.

        Parameters
        ----------
        result:
            Completed assessment result.

        metrics:
            Metrics computed by MetricsService.
        """

        report = Report(
            session_id=result.session_id,
            student_id=result.student_id,
            generated_at=datetime.utcnow(),
            metrics=metrics,
        )

        report.metadata = {
            "completed": result.completed,
            "configuration": result.configuration,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "interviewer_id": result.interviewer_id,
            # v12.6.3: expose the already-projected safe reporting metadata
            # (conversation, ABET traceability, rubric calibration, fairness
            # calibration and integrity) without altering assessment state.
            "assessment_metadata": result.metadata,
            "conversation": result.metadata.get("conversation", []),
        }

        return report