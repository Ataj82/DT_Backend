"""
app/api/routers/interviews.py

HTTP API adapter for student interviews.

Responsibilities
----------------
- Validate HTTP requests through FastAPI/Pydantic schemas.
- Delegate interview operations to the application layer.
- Translate application/domain errors into HTTP responses.
- Convert domain objects into API DTOs through InterviewMapper.

Non-responsibilities
--------------------
This router MUST NOT contain:
- assessment algorithms
- scoring
- mastery calculation
- confidence calculation
- evidence evaluation
- goal navigation
- indicator selection
- question generation
- interview state mutation logic
- persistence logic

Architecture
------------

HTTP
  |
  v
Interview Router
  |
  +--------------------+
  |                    |
  v                    v
AssessmentFramework  InterviewService
  |                    |
  +---------+----------+
            |
            v
       Domain/Application
            |
            v
        InterviewSession
            |
            v
      InterviewMapper
            |
            v
          DTO
"""


from __future__ import annotations

import logging
from contextlib import nullcontext

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies import (
    get_framework,
    get_interview_service,
)

from ...api.mappers.interview_mapper import InterviewMapper

from ...api.schemas.common import InterviewStatus

from ...api.schemas.interviews import (
    AssessmentResultResponse,
    ConversationTurnResponse,
    CreateInterviewRequest,
    InterviewSessionResponse,
    StartInterviewResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)

from ...framework.assessment_framework import AssessmentFramework
from ...assessment.goal_time_manager import GoalTimeManager
from ...services.interview_service import InterviewService
from ...interview.lifecycle import InterviewLifecycle


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/interviews",
    tags=["Interviews"],
)


# ==========================================================
# HTTP error helpers
# ==========================================================


def _not_found(detail: str) -> HTTPException:
    """
    Build a standard HTTP 404 response.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=detail,
    )


def _bad_request(detail: str) -> HTTPException:
    """
    Build a standard HTTP 400 response.
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def _conflict(detail: str) -> HTTPException:
    """
    Build a standard HTTP 409 response.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


# ==========================================================
# Create Interview
# ==========================================================


@router.post(
    "",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_interview(
    request: CreateInterviewRequest,
    framework: AssessmentFramework = Depends(get_framework),
) -> InterviewSessionResponse:
    """
    Create a new interview session.

    Delegation
    ----------
    AssessmentFramework.create_interview()

    The framework/application layer is responsible for:
    - resolving the knowledge model
    - resolving the goal model
    - validating the requested models
    - constructing the interview session
    - initializing assessment state
    - persisting the session

    The router only adapts HTTP input/output.
    """

    try:
        session = framework.create_interview(
            student_id=request.student_id,
            knowledge_id=request.knowledge_id,
            goal_model_id=request.goal_model_id,
            configuration=request.configuration,
        )

    except ValueError as exc:
        raise _bad_request(str(exc)) from exc

    return InterviewMapper.to_session(session)


# ==========================================================
# Start Interview
# ==========================================================


@router.post(
    "/{session_id}/start",
    response_model=StartInterviewResponse,
)
def start_interview(
    session_id: str,
    service: InterviewService = Depends(get_interview_service),
) -> StartInterviewResponse:
    """
    Start an existing interview session.

    Delegation
    ----------
    InterviewService.start_interview()

    The service/application layer owns:
    - session lookup
    - start-state validation
    - runtime creation
    - interview lifecycle rules

    The runtime owns:
    - producing the next turn
    - question generation
    - interview progression

    The router does not decide which question should be asked.
    """

    try:
        with service.session_lock(session_id):
            runtime = service.start_interview(
                session_id
            )

            turn = runtime.next_turn()
            # Persist the generated first turn immediately.  Multi-user launch
            # already does this explicitly, but the canonical /interviews/{id}/start
            # route must satisfy the same lifecycle contract.  Without this save,
            # a direct start/reload could see no current turn and regenerate the
            # first question or reject the first answer as stale.
            service.save(runtime.session)

    except ValueError as exc:
        raise _not_found(str(exc)) from exc

    except RuntimeError as exc:
        raise _conflict(str(exc)) from exc

    elapsed = runtime._elapsed_seconds()
    duration = runtime._duration_seconds()
    snapshot = runtime._goal_time_snapshot()
    current_goal_id = getattr(turn, "goal_id", None)
    current_goal = (snapshot.get("goals", {}) or {}).get(str(current_goal_id), {})
    return StartInterviewResponse(
        session_id=session_id,
        current_goal_id=current_goal_id,
        current_goal_budget_seconds=current_goal.get("budget_seconds"),
        current_goal_elapsed_seconds=current_goal.get("elapsed_seconds"),
        current_goal_remaining_seconds=current_goal.get("remaining_seconds"),
        goal_time_snapshot=snapshot,
        **InterviewMapper._live_metrics(runtime.session),
        status=(
            InterviewStatus.COMPLETED
            if runtime.completed
            else InterviewStatus.RUNNING
        ),
        first_question=turn.question,
        turn_index=int(getattr(turn, "index", 1)),
        duration_seconds=int(duration),
        elapsed_seconds=elapsed,
        remaining_seconds=max(0.0, duration - elapsed),
    )


# ==========================================================
# Get Interview
# ==========================================================


@router.get(
    "/{session_id}",
    response_model=InterviewSessionResponse,
)
def get_interview(
    session_id: str,
    framework: AssessmentFramework = Depends(get_framework),
) -> InterviewSessionResponse:
    """
    Return an existing interview session.

    Assessment state is mapped by InterviewMapper.
    """

    try:
        session = framework.get_session(
            session_id
        )
    except (KeyError, ValueError):
        raise _not_found(
            "Interview session not found."
        )

    return InterviewMapper.to_session(
        session
    )


# ==========================================================
# Submit Answer / Next Turn
# ==========================================================


@router.post(
    "/{session_id}/turn",
    response_model=SubmitAnswerResponse,
)
def next_turn(
    session_id: str,
    request: SubmitAnswerRequest,
    framework: AssessmentFramework = Depends(get_framework),
) -> SubmitAnswerResponse:
    """
    Submit the student's answer and return the evaluation of that answer
    together with the next question.

    Delegation
    ----------
    AssessmentFramework.next_turn()

    The framework/application layer owns the complete interview
    progression pipeline, including:

        answer
          ↓
        evaluation
          ↓
        evidence
          ↓
        assessment state
          ↓
        goal/indicator progression
          ↓
        next question
    """

    try:
        interview_service = getattr(getattr(framework, "services", None), "interview_service", None)
        lock_context = interview_service.session_lock(session_id) if interview_service is not None else nullcontext()
        with lock_context:
            turn = framework.next_turn(
                session_id=session_id,
                answer=request.answer,
                expected_turn_index=request.turn_index,
            )

    except ValueError as exc:
        raise _not_found(str(exc)) from exc

    except RuntimeError as exc:
        raise _conflict(str(exc)) from exc

    session = framework.get_interview(
        session_id
    )

    if session is None:
        raise _not_found(
            "Interview session not found."
        )

    turns = list(getattr(session, "turns", ()) or ())

    # runtime.next_turn() returns the newly generated question for a
    # continuing interview, while the answer/evaluation belongs to the
    # immediately preceding turn. On terminal completion it may return
    # that same answered turn.
    returned_index = next(
        (i for i, persisted_turn in enumerate(turns) if persisted_turn is turn),
        len(turns) - 1,
    )

    if returned_index > 0 and turn is not turns[returned_index - 1]:
        answered_turn = turns[returned_index - 1]
    else:
        answered_turn = turn

    evaluation = InterviewMapper.to_answer_evaluation(
        answered_turn,
        session=session,
    )

    next_question = (
        InterviewMapper.to_question(
            turn,
            session=session,
        )
        if turn is not answered_turn
        else None
    )

    # Protocol invariant: a response either supplies a next question
    # or declares the interview complete. A non-null next_question is
    # authoritative evidence that the interview is continuing.
    #
    # The runtime repairs any stale lifecycle flag before persistence,
    # but keep this boundary defensive: if a continuing turn somehow
    # reaches the API with session.completed=True, expose the protocol
    # implied by the actual returned turn rather than leaking stale state.
    #
    # IMPORTANT: evaluation.status belongs to the answered GOAL. It may
    # be `failed` when that goal is resolved unsuccessfully, while the
    # interview itself must remain RUNNING if another goal has produced
    # the next question. Never derive interview lifecycle from
    # evaluation.status.
    interview_completed, lifecycle_name = InterviewLifecycle.response_state(next_question)
    InterviewLifecycle.assert_response_invariant(
        next_question=next_question,
        interview_completed=interview_completed,
    )

    lifecycle_status = (
        InterviewStatus.COMPLETED
        if lifecycle_name == "completed"
        else InterviewStatus.RUNNING
    )

    logger.info(
        "INTERVIEW LIFECYCLE session=%s answered_turn=%s returned_turn=%s "
        "session_completed=%s response_status=%s interview_completed=%s next_question=%s",
        session_id,
        getattr(answered_turn, "index", None),
        getattr(turn, "index", None),
        getattr(session, "completed", None),
        lifecycle_name,
        interview_completed,
        next_question is not None,
    )

    configuration = getattr(session, "configuration", None)
    duration_value = getattr(configuration, "duration_seconds", None)
    if duration_value is None:
        duration_value = float(getattr(configuration, "max_minutes", 30) or 30) * 60.0
    started_at = getattr(session, "started_at", None)
    if started_at is not None:
        from datetime import datetime, timezone
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
    else:
        elapsed = 0.0

    snapshot = GoalTimeManager(session).snapshot(getattr(next_question, "goal_id", None) if next_question is not None else getattr(answered_turn, "goal_id", None))
    current_goal_id = getattr(next_question, "goal_id", None) if next_question is not None else getattr(answered_turn, "goal_id", None)
    current_goal = (snapshot.get("goals", {}) or {}).get(str(current_goal_id), {})
    return SubmitAnswerResponse(
        evaluation=evaluation,
        next_question=next_question,
        current_goal_id=current_goal_id,
        current_goal_budget_seconds=current_goal.get("budget_seconds"),
        current_goal_elapsed_seconds=current_goal.get("elapsed_seconds"),
        current_goal_remaining_seconds=current_goal.get("remaining_seconds"),
        goal_time_snapshot=snapshot,
        **InterviewMapper._live_metrics(session),
        progress=InterviewMapper.to_session(session).progress,
        status=lifecycle_status,
        interview_completed=interview_completed,
        duration_seconds=int(float(duration_value)),
        elapsed_seconds=elapsed,
        remaining_seconds=max(0.0, float(duration_value) - elapsed),
    )


# ==========================================================
# Assessment Result
# ==========================================================


@router.get(
    "/{session_id}/result",
    response_model=AssessmentResultResponse,
)
def get_result(
    session_id: str,
    framework: AssessmentFramework = Depends(get_framework),
) -> AssessmentResultResponse:
    """
    Return the assessment result for an interview.

    The framework/application layer determines:
    - whether the session exists
    - whether a result is available
    - how the result is calculated

    The router only exposes the result through the API DTO.
    """

    try:
        result = framework.get_assessment_result(
            session_id
        )

    except ValueError as exc:
        raise _not_found(str(exc)) from exc

    if result is None:
        raise _not_found(
            "Assessment result not available."
        )

    return InterviewMapper.to_result(
        result
    )


# ==========================================================
# Complete Interview
# ==========================================================


@router.post(
    "/{session_id}/complete",
    response_model=AssessmentResultResponse,
)
def complete_interview(
    session_id: str,
    framework: AssessmentFramework = Depends(get_framework),
) -> AssessmentResultResponse:
    """
    Complete an interview and return its assessment result.

    The framework/application layer owns completion logic.

    This endpoint MUST NOT independently calculate:
    - mastery
    - score
    - confidence
    - evidence strength
    - pass/fail
    - goal completion
    """

    try:
        interview_service = getattr(getattr(framework, "services", None), "interview_service", None)
        lock_context = interview_service.session_lock(session_id) if interview_service is not None else nullcontext()
        with lock_context:
            result = framework.complete_assessment(
                session_id
            )

    except ValueError as exc:
        raise _not_found(str(exc)) from exc

    except RuntimeError as exc:
        raise _conflict(str(exc)) from exc

    return InterviewMapper.to_result(
        result
    )
# ==========================================================
# ABET Assessment / Traceability
# ==========================================================
@router.get("/{session_id}/assessment")
def get_abet_assessment(session_id: str, framework: AssessmentFramework = Depends(get_framework)):
    try: return framework.get_abet_assessment(session_id)
    except ValueError as exc: raise _not_found(str(exc)) from exc

@router.get("/{session_id}/traceability")
def get_abet_traceability(session_id: str, framework: AssessmentFramework = Depends(get_framework)):
    try:
        data=framework.get_abet_assessment(session_id)
        return {"plan_id":data.get("plan_id"),"traceability":data.get("traceability",[])}
    except ValueError as exc: raise _not_found(str(exc)) from exc


# Exact ABET read-only endpoints; included without the legacy router prefix.
abet_interview_router = APIRouter(tags=["ABET Assessment"])

@abet_interview_router.get("/interviews/{session_id}/assessment")
def exact_abet_assessment(session_id: str, framework: AssessmentFramework = Depends(get_framework)):
    try: return framework.get_abet_assessment(session_id)
    except ValueError as exc: raise _not_found(str(exc)) from exc

@abet_interview_router.get("/interviews/{session_id}/traceability")
def exact_abet_traceability(session_id: str, framework: AssessmentFramework = Depends(get_framework)):
    try:
        data=framework.get_abet_assessment(session_id)
        return {"plan_id":data.get("plan_id"),"traceability":data.get("traceability",[])}
    except ValueError as exc: raise _not_found(str(exc)) from exc
