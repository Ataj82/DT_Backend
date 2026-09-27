"""
app/api/schemas/common.py

Shared API schemas.

These models define common request/response types used
throughout the Adaptive Interview Framework API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from ...knowledge.models import BloomLevel

# ==========================================================
# Base Model
# ==========================================================

class APIModel(BaseModel):
    """
    Base class for all API models.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        extra="forbid",
    )


# ==========================================================
# Enumerations
# ==========================================================

class InterviewStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GoalStatus(str, Enum):
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class StrategyType(str, Enum):
    GOAL_BASED = "goal_based"


class NavigationType(str, Enum):
    ADAPTIVE = "adaptive"
    SEQUENTIAL = "sequential"


class ReportType(str, Enum):
    RESEARCH = "research"
    INSTRUCTOR = "instructor"
    STUDENT = "student"
    ADMINISTRATIVE = "administrative"


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


# ==========================================================
# Shared Identifier Models
# ==========================================================

class Identifier(APIModel):

    id: str = Field(
        ...,
        description="Unique identifier.",
        examples=["goal-001"],
    )


class SessionIdentifier(APIModel):

    session_id: str = Field(
        ...,
        examples=["session-001"],
    )


class StudentIdentifier(APIModel):

    student_id: str = Field(
        ...,
        examples=["student-001"],
    )


# ==========================================================
# Timestamp Model
# ==========================================================

class Timestamped(APIModel):

    created_at: datetime | None = None

    updated_at: datetime | None = None


# ==========================================================
# Pagination
# ==========================================================

class Pagination(APIModel):

    page: int = Field(
        default=1,
        ge=1,
    )

    page_size: int = Field(
        default=20,
        ge=1,
        le=200,
    )


# ==========================================================
# Standard Response
# ==========================================================

class StatusResponse(APIModel):

    success: bool = True

    message: str = "Success"


# ==========================================================
# Error Response
# ==========================================================

class ErrorResponse(APIModel):

    success: bool = False

    error: str

    detail: str | None = None


# ==========================================================
# Generic API Response
# ==========================================================

T = TypeVar("T")


class ApiResponse(APIModel, Generic[T]):
    """
    Standard wrapper for successful API responses.
    """

    success: bool = True

    data: T

    message: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


# ==========================================================
# Health Check
# ==========================================================

class HealthResponse(APIModel):

    status: str = "healthy"

    version: str

    timestamp: datetime


# ==========================================================
# Problem Details (RFC 7807 inspired)
# ==========================================================

class ProblemDetails(APIModel):

    type: str = "about:blank"

    title: str

    status: int

    detail: str

    instance: str | None = None