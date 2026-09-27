"""
app/api/schemas/exam_requests.py

Schemas specifically handling exam creation requests from frontend inputs
(e.g., CreateExamAccordion, Teacher Dashboard, Student Exam View).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import ConfigDict, Field

from .common import APIModel
from .goals import GoalCreateInput, GoalResponse


class ExamCreateRequest(APIModel):
    """
    Direct payload sent by CreateExamAccordion.jsx when a professor schedules an exam.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )

    title: str = Field(min_length=1, max_length=255)

    description: Optional[str] = None

    course_id: Optional[str] = None

    lesson_id: Optional[str] = None

    duration_minutes: int = Field(default=15, ge=1, le=1440)

    # Goals can be strings: ["مفاهیم پردازش موازی", "مدیریت حافظه"] or structured objects or dicts
    goals: list[Union[str, GoalCreateInput, dict[str, Any]]] = Field(default_factory=list)

    student_ids: list[str] = Field(default_factory=list)

    gap_minutes: Optional[int] = Field(default=5, ge=0)

    exam_date: Optional[str] = None

    start_at: Optional[Union[datetime, str]] = None

    end_at: Optional[Union[datetime, str]] = None

    passing_threshold: float = Field(default=0.70, ge=0.0, le=1.0)

    allow_followup_questions: bool = True

    mode: Optional[str] = "quiz"

    pass_score: Optional[int] = Field(default=70, ge=0, le=100)

    is_active: Optional[bool] = True
    materials: Optional[list[Union[str, dict[str, Any]]]] = Field(default_factory=list)


class ExamResponse(APIModel):
    """
    Response returned to frontend after creating or fetching an exam.
    Includes both legacy quiz keys (quiz_id) and pipeline keys (assignment_id, goal_model_id).
    """

    quiz_id: str

    id: str

    assignment_id: str

    goal_model_id: str

    title: str

    description: Optional[str] = None

    course_id: Optional[str] = None

    lesson_id: Optional[str] = None

    duration_minutes: int

    duration_seconds: int

    goal_count: int

    goals: list[Union[str, GoalResponse]] = Field(default_factory=list)

    goal_time_allocations_seconds: dict[str, int] = Field(default_factory=dict)

    student_count: int

    student_ids: list[str] = Field(default_factory=list)

    gap_minutes: Optional[int] = 5

    exam_date: Optional[str] = None

    start_at: Optional[Union[datetime, str]] = None

    end_at: Optional[Union[datetime, str]] = None

    starts_at: Optional[Union[datetime, str]] = None

    ends_at: Optional[Union[datetime, str]] = None

    status: str = "published"

    is_active: bool = True

    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExamSlot(APIModel):
    slot_index: int
    start_time: str
    end_time: str
    is_booked: bool = False
    booked_by_me: bool = False
    student_id: Optional[str] = None


class SlotRescheduleRequest(APIModel):
    slot_index: int
    start_time: str
    end_time: str


class SlotListResponse(APIModel):
    assignment_id: str
    title: str
    course: str = "سیستم عامل"
    exam_date: Optional[str] = None
    window_start: str
    window_end: str
    duration_minutes: int
    gap_minutes: int
    my_slot: Optional[ExamSlot] = None
    slots: list[ExamSlot] = Field(default_factory=list)


class StudentExamCardResponse(APIModel):
    """
    Card view for student exams dashboard.
    """

    id: str

    assignment_id: str

    session_id: Optional[str] = None

    title: str

    course: str

    topic: str

    date: str

    start_at: Optional[str] = None

    end_at: Optional[str] = None

    duration: int

    status: str  # "waiting", "active", "expired", "completed"

    score: Optional[float] = None

    passed: Optional[bool] = None

    window_start: Optional[str] = None

    window_end: Optional[str] = None

    student_slot_start: Optional[str] = None

    student_slot_end: Optional[str] = None

    gap_minutes: Optional[int] = 5


class ExamUpdateRequest(APIModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    gap_minutes: Optional[int] = Field(default=None, ge=0)
    goals: Optional[list[Union[str, GoalCreateInput, dict[str, Any]]]] = None
    student_ids: Optional[list[str]] = None
    exam_date: Optional[str] = None
    start_at: Optional[Union[datetime, str]] = None
    end_at: Optional[Union[datetime, str]] = None
    starts_at: Optional[Union[datetime, str]] = None
    ends_at: Optional[Union[datetime, str]] = None
    is_active: Optional[bool] = None


class TeacherStudentProgress(APIModel):
    student_id: str
    student_name: str
    username: Optional[str] = None
    profile_url: Optional[str] = None
    status: str
    score: Optional[float] = None
    passed: Optional[bool] = None
    slot_start: Optional[str] = None
    slot_end: Optional[str] = None
    session_id: Optional[str] = None
    turns_count: int = 0


class TeacherExamResultsResponse(APIModel):
    assignment_id: str
    title: str
    course: str = "سیستم عامل"
    date: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    duration_minutes: int
    gap_minutes: int = 5
    total_students: int = 0
    completed_students: int = 0
    average_score: Optional[float] = None
    pass_rate: Optional[float] = None
    students: list[TeacherStudentProgress] = Field(default_factory=list)


class TurnDetail(APIModel):
    index: int
    question: str
    answer: str
    feedback: Optional[str] = None
    goal_id: Optional[str] = None
    goal_title: Optional[str] = None
    timestamp: Optional[str] = None
    bloom_level: Optional[str] = None


class GoalMetricDetail(APIModel):
    goal_id: str
    title: str
    score: float = 0.0
    coverage: float = 0.0
    mastery: float = 0.0
    confidence: float = 0.0
    completed: bool = False


class RecommendationDetail(APIModel):
    priority: str
    category: str
    title: str
    description: str
    action: str


class ExamSessionDetailResponse(APIModel):
    session_id: str
    assignment_id: str
    student_id: str
    student_name: Optional[str] = None
    exam_title: str
    course: str = "سیستم عامل"
    score: Optional[float] = None
    passed: Optional[bool] = None
    overall_mastery: Optional[float] = None
    overall_coverage: Optional[float] = None
    overall_confidence: Optional[float] = None
    completed: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: int = 0
    turns: list[TurnDetail] = Field(default_factory=list)
    goals: list[GoalMetricDetail] = Field(default_factory=list)
    recommendations: list[RecommendationDetail] = Field(default_factory=list)
