from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    PROFESSOR = "professor"
    STUDENT = "student"
    ADMIN = "admin"


class AssignmentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class EnrollmentStatus(str, Enum):
    ASSIGNED = "assigned"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class User:
    id: str
    email: str
    display_name: str
    role: UserRole
    password_hash: str
    created_at: datetime = field(default_factory=utc_now)
    active: bool = True


@dataclass(slots=True)
class AssignmentStudent:
    assignment_id: str
    student_id: str
    session_id: str
    status: EnrollmentStatus = EnrollmentStatus.ASSIGNED
    assigned_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class InterviewAssignment:
    id: str
    professor_id: str
    title: str
    description: str
    knowledge_base_id: str
    goal_model_id: str
    duration_seconds: int
    goal_time_allocations_seconds: dict[str, int] | None
    configuration_snapshot: dict[str, Any]
    knowledge_snapshot: Any
    goal_model_snapshot: Any
    created_at: datetime = field(default_factory=utc_now)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: AssignmentStatus = AssignmentStatus.DRAFT
    students: dict[str, AssignmentStudent] = field(default_factory=dict)

    @property
    def student_ids(self) -> list[str]:
        return list(self.students.keys())
