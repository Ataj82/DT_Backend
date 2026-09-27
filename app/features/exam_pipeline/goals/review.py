"""
goals/review.py

Goal review domain models.

A GoalReview represents a professor's evaluation of a generated
GoalModel before it can be used to create interview sessions.

Multiple reviews may exist for the same GoalModel, allowing
versioning, iterative refinement, and auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4


# ============================================================
# Review Status
# ============================================================

class GoalReviewStatus(str, Enum):
    """
    Possible review outcomes.
    """

    PENDING = "pending"

    APPROVED = "approved"

    REJECTED = "rejected"

    REQUIRES_REVISION = "requires_revision"


# ============================================================
# Review Comment
# ============================================================

@dataclass(slots=True)
class ReviewComment:
    """
    A single review comment.

    Allows multiple comments to be recorded during a review.
    """

    author: str

    message: str

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )


# ============================================================
# Goal Review
# ============================================================

@dataclass(slots=True)
class GoalReview:
    """
    Professor review of a GoalModel.
    """

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    goal_model_id: str = ""

    reviewer: str = ""

    status: GoalReviewStatus = GoalReviewStatus.PENDING

    comments: List[ReviewComment] = field(
        default_factory=list
    )

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    reviewed_at: Optional[datetime] = None

    version: int = 1

    # ---------------------------------------------------------

    @property
    def approved(self) -> bool:
        return self.status == GoalReviewStatus.APPROVED

    # ---------------------------------------------------------

    @property
    def pending(self) -> bool:
        return self.status == GoalReviewStatus.PENDING

    # ---------------------------------------------------------

    def add_comment(
        self,
        author: str,
        message: str,
    ) -> None:

        self.comments.append(

            ReviewComment(

                author=author,

                message=message,

            )

        )

    # ---------------------------------------------------------

    def approve(
        self,
        reviewer: str,
    ) -> None:

        self.reviewer = reviewer

        self.status = GoalReviewStatus.APPROVED

        self.reviewed_at = datetime.utcnow()

    # ---------------------------------------------------------

    def reject(
        self,
        reviewer: str,
        reason: str,
    ) -> None:

        self.reviewer = reviewer

        self.status = GoalReviewStatus.REJECTED

        self.reviewed_at = datetime.utcnow()

        self.add_comment(
            reviewer,
            reason,
        )

    # ---------------------------------------------------------

    def request_revision(
        self,
        reviewer: str,
        reason: str,
    ) -> None:

        self.reviewer = reviewer

        self.status = (
            GoalReviewStatus.REQUIRES_REVISION
        )

        self.reviewed_at = datetime.utcnow()

        self.add_comment(
            reviewer,
            reason,
        )