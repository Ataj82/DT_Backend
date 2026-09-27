"""
app/api/routers/goal_router.py

REST API endpoints for GoalModels.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from ...api.dependencies import get_framework
from ...api.mappers.goal_mapper import GoalMapper
from ...api.schemas.goals import (
    GenerateGoalsRequest,
    GenerateGoalsResponse,
    GoalListResponse,
    GoalModelCreateRequest,
    GoalResponse,
    ReviewGoalsRequest,
    ReviewGoalsResponse,
)
from ...goals.models import GoalModel
from ...framework.assessment_framework import (
    AssessmentFramework,
)

router = APIRouter(
    prefix="/goals",
    tags=["Goals"],
)


# ==========================================================
# Generate Goals
# ==========================================================

@router.post(
    "/generate",
    response_model=GenerateGoalsResponse,
    status_code=status.HTTP_201_CREATED,
)

def generate_goals(
    request: GenerateGoalsRequest,
    framework: AssessmentFramework = Depends(get_framework),
):
    """
    Generate assessment goals from a knowledge base.
    """
    import traceback

    try:
        goal_model = framework.generate_goals(
            knowledge_id=request.knowledge_id,
            max_goals=request.max_goals,
            include_optional=request.include_optional,
        )

    except Exception:
        traceback.print_exc()
        raise

    return GoalMapper.to_generate_response(goal_model)


# ==========================================================
# Create Goal Model Directly
# ==========================================================

@router.post(
    "",
    response_model=GenerateGoalsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create GoalModel directly from goals data",
)
def create_goal_model(
    request: GoalModelCreateRequest,
    framework: AssessmentFramework = Depends(get_framework),
):
    """
    Directly create and persist a GoalModel from goals input (strings or objects).
    """
    goals_data = [g.model_dump() if hasattr(g, "model_dump") else g for g in request.goals]
    model = GoalModel.create_from_input(
        knowledge_base_id=request.knowledge_base_id,
        goals_data=goals_data,
        title=request.title,
        course_id=request.course_id,
        lesson_id=request.lesson_id,
        total_duration_minutes=request.duration_minutes,
    )
    framework.services.goal_service.save(model)
    return GoalMapper.to_generate_response(model)
# ==========================================================
# Review Goals
# ==========================================================

@router.post(
    "/review",
    response_model=ReviewGoalsResponse,
)
def review_goals(
    request: ReviewGoalsRequest,
    framework: AssessmentFramework = Depends(
        get_framework
    ),
):
    """
    Approve or reject generated goals.
    """

    approved_goal_ids = [

        review.goal_id

        for review in request.reviews

        if review.approved

    ]

    try:

        goal_model = framework.review_goals(

            goal_model_id=request.goal_model_id,

            approved_goal_ids=approved_goal_ids,

        )

    except ValueError as exc:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail=str(exc),

        )

    rejected = [

        review.goal_id

        for review in request.reviews

        if not review.approved

    ]

    return GoalMapper.to_review_response(

        goal_model,

        rejected_goal_ids=rejected,

    )


# ==========================================================
# List Goal Models
# ==========================================================

@router.get(
    "",
    response_model=list[GoalListResponse],
)
def list_goal_models(
    framework: AssessmentFramework = Depends(get_framework),
):
    """Return all goal models for course/goal management UIs."""

    return [
        GoalMapper.to_goal_list(goal_model)
        for goal_model in framework.list_goal_models()
    ]


# ==========================================================
# Get Goal Model
# ==========================================================

@router.get(
    "/{goal_model_id}",
    response_model=GoalListResponse,
)
def get_goal_model(
    goal_model_id: str,
    framework: AssessmentFramework = Depends(
        get_framework
    ),
):
    """
    Retrieve a GoalModel.
    """

    goal_model = framework.get_goal_model(
        goal_model_id
    )

    if goal_model is None:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Goal model not found.",

        )

    return GoalMapper.to_goal_list(
        goal_model
    )


# ==========================================================
# Get Goal
# ==========================================================

@router.get(
    "/{goal_model_id}/{goal_id}",
    response_model=GoalResponse,
)
def get_goal(
    goal_model_id: str,
    goal_id: str,
    framework: AssessmentFramework = Depends(
        get_framework
    ),
):
    """
    Retrieve a single goal.
    """

    goal_model = framework.get_goal_model(
        goal_model_id
    )

    if goal_model is None:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Goal model not found.",

        )

    goal = goal_model.get_goal(
        goal_id
    )

    if goal is None:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Goal not found.",

        )

    return GoalMapper.to_goal(
        goal
    )


# ==========================================================
# Delete Goal Model
# ==========================================================

@router.delete(
    "/{goal_model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_goal_model(
    goal_model_id: str,
    framework: AssessmentFramework = Depends(
        get_framework
    ),
):
    """
    Delete a GoalModel.
    """

    framework.delete_goal_model(
        goal_model_id
    )