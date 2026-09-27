"""
Domain event definitions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import DomainEvent


@dataclass(slots=True)
class InterviewCreated(DomainEvent):

    session_id: str = ""

    student_id: str = ""


@dataclass(slots=True)
class QuestionGenerated(DomainEvent):

    session_id: str = ""

    question: str = ""

    indicator_id: str = ""


@dataclass(slots=True)
class AnswerReceived(DomainEvent):

    session_id: str = ""

    answer: str = ""


@dataclass(slots=True)
class GoalCompleted(DomainEvent):

    session_id: str = ""

    goal_id: str = ""


@dataclass(slots=True)
class InterviewCompleted(DomainEvent):

    session_id: str = ""


@dataclass(slots=True)
class ReportGenerated(DomainEvent):

    session_id: str = ""