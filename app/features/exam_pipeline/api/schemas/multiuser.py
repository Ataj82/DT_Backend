from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .common import APIModel


class RegisterRequest(APIModel):
    email: str
    display_name: str
    password: str = Field(min_length=8)
    role: str = Field(pattern=r"^(professor|student)$")


class LoginRequest(APIModel):
    email: str
    password: str


class UserResponse(APIModel):
    id: str
    email: str
    display_name: str
    role: str


class LoginResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateAssignmentRequest(APIModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    knowledge_base_id: str
    goal_model_id: str
    duration_seconds: int = Field(default=600, ge=30, le=86400)
    goal_time_allocations_seconds: dict[str, int] | None = None
    passing_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    allow_followup_questions: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EnrollStudentsRequest(APIModel):
    student_ids: list[str] = Field(min_length=1)


class AssignmentResponse(APIModel):
    id: str
    professor_id: str
    title: str
    description: str
    knowledge_base_id: str
    goal_model_id: str
    duration_seconds: int
    goal_time_allocations_seconds: dict[str, int] | None
    status: str
    starts_at: datetime | None
    ends_at: datetime | None
    student_count: int


class EnrollmentResponse(APIModel):
    assignment_id: str
    student_id: str
    session_id: str
    status: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class StudentAssignmentResponse(APIModel):
    assignment: AssignmentResponse
    enrollment: EnrollmentResponse


class AssignmentStudentProgressResponse(APIModel):
    student_id: str
    session_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    interview_completed: bool
    turns: int
    score: float | None = None
    passed: bool | None = None


class GoalIndicatorEditRequest(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    required: bool = True
    weight: float = Field(default=1.0, ge=0.0)
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0)


class GoalEditRequest(APIModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    bloom_level: str
    importance: float = Field(default=1.0, ge=0.0)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_questions: int = Field(default=4, ge=1, le=50)
    status: str | None = None


class CreateGoalRequest(APIModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    bloom_level: str = "understand"
    importance: float = Field(default=1.0, ge=0.0)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_questions: int = Field(default=4, ge=1, le=50)
    indicator: GoalIndicatorEditRequest


class PreparationGoalModelResponse(APIModel):
    goal_model_id: str
    knowledge_base_id: str
    version: str
    goal_count: int
    goals: list[dict]
