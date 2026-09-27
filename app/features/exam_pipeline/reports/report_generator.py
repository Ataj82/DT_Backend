"""
reports/report_generator.py

Abstract report generator.

A report generator transforms an AssessmentResult into
a presentation-specific report.

Different generators may produce reports for instructors,
students, researchers, administrators, or external systems.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..assessment.result import AssessmentResult


class ReportGenerator(ABC):
    """
    Base class for all report generators.
    """

    @abstractmethod
    def build(
        self,
        result: AssessmentResult,
    ):
        """
        Build a report from an AssessmentResult.
        """
        raise NotImplementedError