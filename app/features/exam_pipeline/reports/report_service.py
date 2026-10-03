"""
app/services/report_service.py

Application service responsible for generating assessment reports.

The service coordinates:

    AssessmentResult
            │
            ▼
    MetricsService
            │
            ▼
    ResearchReportGenerator
            │
            ▼
      AssessmentReport

This service contains no reporting logic itself.
"""

from __future__ import annotations

from ..reports.metrics_service import MetricsService
from ..reports.research_report_generator import (
    ResearchReportGenerator,
)


class ReportService:
    """
    Builds research reports from completed assessment results.
    """

    def __init__(
        self,
        *,
        metrics_service: MetricsService,
        generator: ResearchReportGenerator,
    ):
        self.metrics_service = metrics_service
        self.generator = generator

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def generate(
        self,
        session_id: str,
        assessment_result=None,
    ):
        """Backward-compatible report generation façade.

        ``assessment_result`` may be supplied by the framework; otherwise
        callers should use AssessmentFramework.build_report().
        """
        if assessment_result is None:
            raise ValueError("assessment_result is required when using ReportService directly.")
        return self.build_report(assessment_result)

    def export(
        self,
        report,
        format: str,
    ) -> tuple[bytes, str, str]:
        """Render a report without changing assessment state."""
        from .exporters import render_html, render_json, render_pdf
        fmt = str(format).lower().strip()
        if fmt == "json":
            return render_json(report), "application/json", "json"
        if fmt == "html":
            return render_html(report), "text/html; charset=utf-8", "html"
        if fmt == "pdf":
            raise ValueError(
                "PDF export is not supported on the backend. "
                "Exam reports are served as structured JSON for frontend rendering."
            )
        raise ValueError("Unsupported report format. Use json or html.")

    # ---------------------------------------------------------

    def build_report(
        self,
        assessment_result,
    ):
        """
        Generate a complete research report.
        """

        metrics = self.metrics_service.compute(
            assessment_result
        )

        return self.generator.build(
            result=assessment_result,
            metrics=metrics,
        )

    # ---------------------------------------------------------

    def build_metrics(
        self,
        assessment_result,
    ):
        """
        Compute metrics only.
        """

        return self.metrics_service.compute(
            assessment_result
        )