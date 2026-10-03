from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..header_utils import content_disposition_attachment
from ..dependencies_multiuser import get_current_user, get_multiuser_service, require_professor, require_student
from ..dependencies import get_framework
from ..schemas.multiuser import (
    AssignmentResponse,
    AssignmentStudentProgressResponse,
    CreateAssignmentRequest,
    EnrollmentResponse,
    EnrollStudentsRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    StudentAssignmentResponse,
    UserResponse,
    UpdateProfileRequest,
    GoalEditRequest,
    CreateGoalRequest,
    PreparationGoalModelResponse,
)
from ...multiuser.models import User, UserRole
from ...goals.models import Goal, GoalIndicator, GoalStatus, IndicatorType
from ...knowledge.models import BloomLevel
from uuid import uuid4

router = APIRouter(prefix="/multiuser", tags=["Multi-user"])


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate({"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role.value, "preferred_language": getattr(user, "preferred_language", None)})


def _assignment_response(assignment) -> AssignmentResponse:
    return AssignmentResponse.model_validate({
        "id": assignment.id,
        "professor_id": assignment.professor_id,
        "title": assignment.title,
        "description": assignment.description,
        "knowledge_base_id": assignment.knowledge_base_id,
        "goal_model_id": assignment.goal_model_id,
        "duration_seconds": assignment.duration_seconds,
        "goal_time_allocations_seconds": assignment.goal_time_allocations_seconds,
        "status": assignment.status.value,
        "starts_at": assignment.starts_at,
        "ends_at": assignment.ends_at,
        "student_count": len(assignment.students),
        "language": str((assignment.configuration_snapshot or {}).get("language") or (getattr(assignment.knowledge_snapshot, "metadata", {}) or {}).get("language", "en")),
    })


def _enrollment_response(enrollment) -> EnrollmentResponse:
    return EnrollmentResponse.model_validate({
        "assignment_id": enrollment.assignment_id,
        "student_id": enrollment.student_id,
        "session_id": enrollment.session_id,
        "status": enrollment.status.value,
        "assigned_at": enrollment.assigned_at,
        "started_at": enrollment.started_at,
        "completed_at": enrollment.completed_at,
    })


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, service=Depends(get_multiuser_service)):
    try:
        role = UserRole(request.role)
        user = service.register(email=request.email, display_name=request.display_name, password=request.password, role=role)
        return _user_response(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, service=Depends(get_multiuser_service)):
    try:
        user, token = service.login(email=request.email, password=request.password)
        return LoginResponse(access_token=token, user=_user_response(user))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return _user_response(user)


@router.patch("/auth/profile", response_model=UserResponse)
def update_profile(request: UpdateProfileRequest, user: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        updated = service.update_profile_language(user=user, preferred_language=request.preferred_language)
        return _user_response(updated)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/students", response_model=list[UserResponse])
def list_students(user: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    return [_user_response(x) for x in service.repository.list_users(UserRole.STUDENT)]


@router.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(request: CreateAssignmentRequest, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        assignment = service.create_assignment(
            professor=professor,
            title=request.title,
            description=request.description,
            knowledge_base_id=request.knowledge_base_id,
            goal_model_id=request.goal_model_id,
            duration_seconds=request.duration_seconds,
            goal_time_allocations_seconds=request.goal_time_allocations_seconds,
            passing_threshold=request.passing_threshold,
            allow_followup_questions=request.allow_followup_questions,
            language=request.language,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
        )
        return _assignment_response(assignment)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assignments", response_model=list[AssignmentResponse])
def list_assignments(professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    return [_assignment_response(x) for x in service.professor_assignments(professor=professor)]


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(assignment_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        return _assignment_response(service.assignment_detail(professor=professor, assignment_id=assignment_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/assignments/{assignment_id}/students", response_model=AssignmentResponse)
def enroll_students(assignment_id: str, request: EnrollStudentsRequest, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        assignment = service.enroll_students(professor=professor, assignment_id=assignment_id, student_ids=request.student_ids)
        return _assignment_response(assignment)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assignments/{assignment_id}/publish", response_model=AssignmentResponse)
def publish_assignment(assignment_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        return _assignment_response(service.publish_assignment(professor=professor, assignment_id=assignment_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assignments/{assignment_id}/close", response_model=AssignmentResponse)
def close_assignment(assignment_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        return _assignment_response(service.close_assignment(professor=professor, assignment_id=assignment_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assignments/{assignment_id}/students", response_model=list[AssignmentStudentProgressResponse])
def assignment_students(assignment_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    try:
        _, rows = service.assignment_student_sessions(professor=professor, assignment_id=assignment_id)
        result = []
        for enrollment, session in rows:
            score = None
            passed = None
            if session is not None and getattr(session, "completed", False):
                try:
                    assessment = service.interview_service.get_session(enrollment.session_id)
                    # Keep report/scoring ownership in existing framework services;
                    # this route only exposes a compact status view.
                    result_obj = service.interview_service.runtime_factory.create(session=assessment).build_result()
                    score = getattr(result_obj, "score", None)
                    passed = getattr(result_obj, "passed", None)
                except Exception:
                    pass
            result.append(AssignmentStudentProgressResponse(
                student_id=enrollment.student_id,
                session_id=enrollment.session_id,
                status=enrollment.status.value,
                started_at=enrollment.started_at,
                completed_at=enrollment.completed_at,
                interview_completed=bool(session and getattr(session, "completed", False)),
                turns=len(getattr(session, "turns", []) or []) if session else 0,
                score=score,
                passed=passed,
            ))
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc




# ----------------------------------------------------------
# Role-scoped reports
# ----------------------------------------------------------

def _export_session_report(service, session_id: str, fmt: str):
    # The canonical framework owns result/report generation.  Import the provider
    # here to avoid changing the existing interview/report architecture.
    from ..dependencies import get_framework
    fw = get_framework()
    report = fw.build_report(session_id)
    payload, media_type, extension = fw.services.report_service.export(report, fmt)
    return payload, media_type, extension


def _require_completed_session(session):
    if session is None:
        raise ValueError("Interview session not found.")
    if not getattr(session, "completed", False):
        raise ValueError("The detailed interview report is available after the interview is completed.")


@router.get("/my/assignments/{assignment_id}/report/{format}")
def student_report(
    assignment_id: str,
    format: str,
    student: User = Depends(require_student),
    service=Depends(get_multiuser_service),
):
    try:
        assignment, enrollment, session = service.get_student_session(student=student, assignment_id=assignment_id)
        _require_completed_session(session)
        payload, media_type, extension = _export_session_report(service, enrollment.session_id, format)
        filename = f"{assignment.title.strip() or 'interview'}-{enrollment.session_id}.{extension}"
        fallback = f"interview-report-{enrollment.session_id}.{extension}"
        return Response(
            content=payload,
            media_type=media_type,
            headers={"Content-Disposition": content_disposition_attachment(filename, fallback=fallback)},
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/my/assignments/{assignment_id}/integrity")
def student_integrity(
    assignment_id: str,
    student: User = Depends(require_student),
    service=Depends(get_multiuser_service),
):
    try:
        assignment, enrollment, session = service.get_student_session(student=student, assignment_id=assignment_id)
        _require_completed_session(session)
        from ..dependencies import get_framework
        return get_framework().verify_assessment_integrity(enrollment.session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _assignment_summary_html(assignment, rows):
    import html
    from ..dependencies import get_framework

    completed = sum(1 for r in rows if r[1] is not None and getattr(r[1], "completed", False))
    lines = []
    for enrollment, session in rows:
        score = coverage = mastery = None
        passed = None
        goals_completed = None
        questions = len(getattr(session, "turns", []) or []) if session else 0
        if session is not None and getattr(session, "completed", False):
            try:
                report = get_framework().build_report(enrollment.session_id)
                metrics = report.metrics
                score = metrics.overall_score
                mastery = metrics.overall_score
                coverage = metrics.overall_coverage
                goals_completed = sum(1 for g in metrics.goal_metrics if g.completed)
                result = get_framework().build_result(enrollment.session_id)
                passed = getattr(result, "passed", None)
            except Exception:
                pass
        lines.append((enrollment.student_id, enrollment.status.value, questions, mastery, coverage, goals_completed, len(getattr(session, "goal_states", {}) or {}) if session else None, passed, enrollment.completed_at))
    rows_html = "".join(
        f"<tr><td>{html.escape(str(student_id))}</td><td>{html.escape(status)}</td><td>{turns}</td>"
        f"<td>{'' if mastery is None else f'{float(mastery):.3f}'}</td><td>{'' if coverage is None else f'{float(coverage):.3f}'}</td>"
        f"<td>{'' if goals_completed is None else f'{goals_completed}/{goal_count or 0}'}</td>"
        f"<td>{'Yes' if passed is True else ('No' if passed is False else '—')}</td>"
        f"<td>{html.escape(str(completed_at or ''))}</td></tr>"
        for student_id, status, turns, mastery, coverage, goals_completed, goal_count, passed, completed_at in lines
    )
    title=html.escape(assignment.title)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Assignment Report — {title}</title>
<style>body{{font-family:Arial,sans-serif;margin:36px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:8px;text-align:left}}th{{background:#f3f3f3}}.metric{{font-size:20px;font-weight:bold}}</style></head><body>
<h1>Assignment Progress Report</h1><p><b>Assignment:</b> {title}</p><p class='metric'>Completed: {completed} / {len(rows)}</p>
<table><tr><th>Student ID</th><th>Status</th><th>Turns</th><th>Mastery</th><th>Coverage</th><th>Goals completed</th><th>Passed</th><th>Completed at</th></tr>{rows_html}</table>
<p><small>Use the detailed student report for Bloom levels, evidence, conversation, adaptive decisions, timing and assessment diagnostics.</small></p></body></html>""".encode("utf-8")


@router.get("/assignments/{assignment_id}/report/{format}")
def professor_assignment_report(
    assignment_id: str,
    format: str,
    professor: User = Depends(require_professor),
    service=Depends(get_multiuser_service),
):
    try:
        assignment, rows = service.assignment_student_sessions(professor=professor, assignment_id=assignment_id)
        fmt = str(format).lower().strip()
        if fmt == "json":
            from ..dependencies import get_framework
            summary = []
            for enrollment, session in rows:
                score = coverage = mastery = None
                passed = None
                goals_completed = goal_count = None
                if session is not None and getattr(session, "completed", False):
                    try:
                        report = get_framework().build_report(enrollment.session_id)
                        score = report.metrics.overall_score
                        mastery = report.metrics.overall_score
                        coverage = report.metrics.overall_coverage
                        goals_completed = sum(1 for g in report.metrics.goal_metrics if g.completed)
                        goal_count = len(report.metrics.goal_metrics)
                        result = get_framework().build_result(enrollment.session_id)
                        passed = getattr(result, "passed", None)
                    except Exception:
                        pass
                summary.append({
                    "student_id": enrollment.student_id,
                    "session_id": enrollment.session_id,
                    "status": enrollment.status.value,
                    "turns": len(getattr(session, "turns", []) or []) if session else 0,
                    "completed": bool(session and getattr(session, "completed", False)),
                    "mastery": mastery,
                    "score": score,
                    "coverage": coverage,
                    "goals_completed": goals_completed,
                    "goal_count": goal_count,
                    "passed": passed,
                    "started_at": enrollment.started_at.isoformat() if enrollment.started_at else None,
                    "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
                })
            payload=json.dumps({"assignment_id": assignment.id, "title": assignment.title, "student_count": len(rows), "completed_count": sum(1 for x in summary if x["completed"]), "students": summary}, indent=2).encode("utf-8")
            return Response(content=payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="assignment-report-{assignment.id}.json"'})
        if fmt == "html":
            return Response(content=_assignment_summary_html(assignment, rows), media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="assignment-report-{assignment.id}.html"'})
        raise ValueError("Assignment summary supports json or html.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@router.get("/assignments/{assignment_id}/students/{student_id}/report/{format}")
def professor_student_report(
    assignment_id: str,
    student_id: str,
    format: str,
    professor: User = Depends(require_professor),
    service=Depends(get_multiuser_service),
):
    try:
        assignment, rows = service.assignment_student_sessions(professor=professor, assignment_id=assignment_id)
        enrollment = assignment.students.get(student_id)
        if enrollment is None:
            raise ValueError("Student is not enrolled in this assignment.")
        session = service.interview_service.get_session(enrollment.session_id)
        _require_completed_session(session)
        payload, media_type, extension = _export_session_report(service, enrollment.session_id, format)
        return Response(content=payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="student-report-{student_id}-{enrollment.session_id}.{extension}"'})
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not enrolled" in str(exc).lower() else 400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/assignments/{assignment_id}/students/{student_id}/integrity")
def professor_student_integrity(
    assignment_id: str,
    student_id: str,
    professor: User = Depends(require_professor),
    service=Depends(get_multiuser_service),
):
    try:
        assignment = service.assignment_detail(professor=professor, assignment_id=assignment_id)
        enrollment = assignment.students.get(student_id)
        if enrollment is None:
            raise ValueError("Student is not enrolled in this assignment.")
        session = service.interview_service.get_session(enrollment.session_id)
        _require_completed_session(session)
        from ..dependencies import get_framework
        return get_framework().verify_assessment_integrity(enrollment.session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not enrolled" in str(exc).lower() else 400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ----------------------------------------------------------
# Professor goal preparation / authoring
# ----------------------------------------------------------

@router.get("/preparation/goal-models/{goal_model_id}", response_model=PreparationGoalModelResponse)
def preparation_goal_model(goal_model_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    model = service.goal_service.get(goal_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Goal model not found.")
    return PreparationGoalModelResponse(
        goal_model_id=model.id,
        knowledge_base_id=model.knowledge_base_id,
        version=model.version,
        goal_count=len(model.goals),
        goals=[g.model_dump(mode="json") for g in model.goals],
    )


@router.patch("/preparation/goal-models/{goal_model_id}/goals/{goal_id}", response_model=PreparationGoalModelResponse)
def edit_preparation_goal(goal_model_id: str, goal_id: str, request: GoalEditRequest, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    model = service.goal_service.get(goal_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Goal model not found.")
    goal = model.get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    try:
        goal.bloom_level = BloomLevel(request.bloom_level)
        goal.title = request.title.strip()
        goal.description = request.description
        goal.importance = request.importance
        goal.difficulty = request.difficulty
        goal.estimated_questions = request.estimated_questions
        if request.status is not None:
            goal.status = GoalStatus(request.status)
        model.version = str(float(model.version) + 0.1) if model.version.replace('.', '', 1).isdigit() else model.version
        service.goal_service.save(model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PreparationGoalModelResponse(goal_model_id=model.id, knowledge_base_id=model.knowledge_base_id, version=model.version, goal_count=len(model.goals), goals=[g.model_dump(mode="json") for g in model.goals])


@router.post("/preparation/goal-models/{goal_model_id}/goals", response_model=PreparationGoalModelResponse)
def add_preparation_goal(goal_model_id: str, request: CreateGoalRequest, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    model = service.goal_service.get(goal_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Goal model not found.")
    try:
        bloom = BloomLevel(request.bloom_level)
        indicator = GoalIndicator(
            id=str(uuid4()),
            name=request.indicator.name.strip(),
            indicator_type=IndicatorType.CONCEPT,
            description=request.indicator.description,
            required=request.indicator.required,
            weight=request.indicator.weight,
            difficulty=request.indicator.difficulty,
        )
        model.goals.append(Goal(
            id=str(uuid4()),
            title=request.title.strip(),
            description=request.description,
            bloom_level=bloom,
            importance=request.importance,
            difficulty=request.difficulty,
            estimated_questions=request.estimated_questions,
            indicators=[indicator],
            status=GoalStatus.GENERATED,
        ))
        service.goal_service.save(model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PreparationGoalModelResponse(goal_model_id=model.id, knowledge_base_id=model.knowledge_base_id, version=model.version, goal_count=len(model.goals), goals=[g.model_dump(mode="json") for g in model.goals])


@router.delete("/preparation/goal-models/{goal_model_id}/goals/{goal_id}", response_model=PreparationGoalModelResponse)
def delete_preparation_goal(goal_model_id: str, goal_id: str, professor: User = Depends(require_professor), service=Depends(get_multiuser_service)):
    model = service.goal_service.get(goal_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Goal model not found.")
    before = len(model.goals)
    model.goals = [g for g in model.goals if g.id != goal_id]
    if len(model.goals) == before:
        raise HTTPException(status_code=404, detail="Goal not found.")
    if not model.goals:
        raise HTTPException(status_code=400, detail="A goal model must contain at least one goal.")
    service.goal_service.save(model)
    return PreparationGoalModelResponse(goal_model_id=model.id, knowledge_base_id=model.knowledge_base_id, version=model.version, goal_count=len(model.goals), goals=[g.model_dump(mode="json") for g in model.goals])


@router.get("/my/assignments", response_model=list[StudentAssignmentResponse])
def my_assignments(student: User = Depends(require_student), service=Depends(get_multiuser_service)):
    result = []
    for assignment, enrollment in service.student_assignments(student=student):
        service.sync_enrollment_status(assignment=assignment, enrollment=enrollment)
        result.append(StudentAssignmentResponse(assignment=_assignment_response(assignment), enrollment=_enrollment_response(enrollment)))
    return result




@router.post("/my/assignments/{assignment_id}/launch", response_model=dict)
async def launch_my_assignment(
    assignment_id: str,
    student: User = Depends(require_student),
    service=Depends(get_multiuser_service),
    framework=Depends(get_framework),
):
    try:
        assignment = service.repository.get_assignment(assignment_id)
        if not assignment:
            from .exam_requests import _sync_db_quizzes_to_pipeline
            await _sync_db_quizzes_to_pipeline(service, framework, student_id_str=str(student.id))
            assignment = service.repository.get_assignment(assignment_id)

        if not assignment:
            raise HTTPException(status_code=404, detail="آزمون یافت نشد.")

        # Ensure student is enrolled in assignment
        enrollment = assignment.students.get(str(student.id))
        config_snapshot = assignment.configuration_snapshot or {}
        student_slots = config_snapshot.setdefault("student_slots", {})

        if not enrollment:
            import copy
            from ...api.schemas.interviews import InterviewConfigurationRequest
            from ...multiuser.models import AssignmentStudent, User as PipelineUser, UserRole as PipelineUserRole
            if not service.repository.get_user(str(student.id)):
                service.repository.save_user(
                    PipelineUser(
                        id=str(student.id),
                        email=getattr(student, "email", f"{student.id}@dt.internal"),
                        display_name=getattr(student, "display_name", f"Student {student.id}"),
                        password_hash="",
                        role=PipelineUserRole.STUDENT,
                    )
                )
            config = InterviewConfigurationRequest.model_validate(config_snapshot)
            session = service.interview_service.create_session(
                student_id=str(student.id),
                knowledge_model=copy.deepcopy(assignment.knowledge_snapshot),
                goal_model=copy.deepcopy(assignment.goal_model_snapshot),
                configuration=config,
                interviewer_id=assignment.professor_id,
            )
            enrollment = AssignmentStudent(
                assignment_id=assignment.id,
                student_id=str(student.id),
                session_id=session.id,
            )
            assignment.students[str(student.id)] = enrollment
            service.repository.save_assignment(assignment)

        # Check student slot timing
        slot_info = student_slots.get(str(student.id))

        from ...multiuser.models import EnrollmentStatus
        if enrollment and enrollment.status == EnrollmentStatus.ASSIGNED and slot_info:
            from datetime import datetime, timezone, timedelta
            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            now_tehran = datetime.now(timezone.utc).astimezone(tehran_tz)
            cur_mins = now_tehran.hour * 60 + now_tehran.minute

            s_str = slot_info.get("start_time")
            e_str = slot_info.get("end_time")
            if s_str and e_str and ":" in s_str and ":" in e_str:
                sh, sm = map(int, s_str.split(":"))
                eh, em = map(int, e_str.split(":"))
                slot_start_mins = sh * 60 + sm
                slot_end_mins = eh * 60 + em

                # Allow 1-2 minutes early buffer for entering room
                if cur_mins < slot_start_mins - 2:
                    diff = slot_start_mins - cur_mins
                    diff_str = f"{diff} دقیقه دیگر" if diff < 60 else f"{diff // 60} ساعت و {diff % 60} دقیقه دیگر"
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"نوبت حضور شما هنوز فرا نرسیده است ({diff_str} - ساعت {s_str}). امکان ورود قبل از نوبت وجود ندارد.",
                    )

                overall_end_mins = 24 * 60
                if assignment.ends_at:
                    end_dt = assignment.ends_at.astimezone(tehran_tz) if assignment.ends_at.tzinfo else assignment.ends_at
                    overall_end_mins = end_dt.hour * 60 + end_dt.minute

                if cur_mins > slot_end_mins:
                    if cur_mins <= overall_end_mins:
                        # Overall window is still active! Find current or next available slot for this student
                        dur_mins = assignment.duration_seconds // 60
                        gap_mins = config_snapshot.get("gap_minutes", 5)
                        from .exam_requests import _generate_time_slots
                        _, _, all_slots = _generate_time_slots(
                            assignment.starts_at,
                            assignment.ends_at,
                            duration_minutes=dur_mins,
                            gap_minutes=gap_mins,
                            student_slots=student_slots,
                            current_student_id=str(student.id),
                        )
                        found_slot = None
                        for sl in all_slots:
                            ssh, ssm = map(int, sl.start_time.split(":"))
                            seh, sem = map(int, sl.end_time.split(":"))
                            smins = ssh * 60 + ssm
                            emins = seh * 60 + sem
                            if smins - 2 <= cur_mins <= emins and (not sl.is_booked or sl.booked_by_me):
                                found_slot = sl
                                break
                        if not found_slot:
                            for sl in all_slots:
                                seh, sem = map(int, sl.end_time.split(":"))
                                emins = seh * 60 + sem
                                if cur_mins <= emins and (not sl.is_booked or sl.booked_by_me):
                                    found_slot = sl
                                    break
                        if found_slot:
                            student_slots[str(student.id)] = {
                                "slot_index": found_slot.slot_index,
                                "start_time": found_slot.start_time,
                                "end_time": found_slot.end_time,
                            }
                            config_snapshot["student_slots"] = student_slots
                            assignment.configuration_snapshot = config_snapshot
                            service.repository.save_assignment(assignment)
                        else:
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"بازه کلی برگزاری این آزمون به پایان رسیده است.",
                            )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"بازه کلی برگزاری این آزمون به پایان رسیده است.",
                        )

        enrollment = service.mark_started(student=student, assignment_id=assignment_id)
        runtime = service.interview_service.start_interview(enrollment.session_id)

        # Check if interview is already completed or duration expired
        is_completed = runtime.completed or runtime._time_expired()
        if is_completed:
            if not runtime.completed:
                runtime.session.completed = True
                service.interview_service.save(runtime.session)
            service.sync_enrollment_status(assignment=assignment, enrollment=enrollment)
            last_turn = runtime.current_turn
            question = (getattr(last_turn, "question", None) or getattr(last_turn, "text", None)) if last_turn else "آزمون به پایان رسیده است."
            from ..mappers.interview_mapper import InterviewMapper
            from ...assessment.goal_time_manager import GoalTimeManager
            snapshot = GoalTimeManager(runtime.session).snapshot(getattr(last_turn, "goal_id", None) if last_turn else None)
            live = InterviewMapper._live_metrics(runtime.session)
            return {
                "assignment_id": assignment_id,
                "session_id": enrollment.session_id,
                "status": "completed",
                "interview_completed": True,
                "first_question": question.model_dump(mode="json") if hasattr(question, "model_dump") else question,
                "turn_index": getattr(last_turn, "index", None),
                "duration_seconds": runtime._duration_seconds(),
                "elapsed_seconds": runtime._elapsed_seconds(),
                "remaining_seconds": 0.0,
                "current_goal_id": getattr(last_turn, "goal_id", None) if last_turn else None,
                "goal_time_snapshot": snapshot,
                **live,
            }

        # If session has no turns yet, generate the initial question.
        # If it already has an active turn, reuse it so student can answer without error.
        turn = runtime.current_turn
        if turn is None:
            turn = runtime.next_turn()
            service.interview_service.save(runtime.session)

        question = getattr(turn, "question", None)
        if question is None:
            question = getattr(turn, "text", None)
        from ..mappers.interview_mapper import InterviewMapper
        from ...assessment.goal_time_manager import GoalTimeManager
        snapshot = GoalTimeManager(runtime.session).snapshot(getattr(turn, "goal_id", None))
        live = InterviewMapper._live_metrics(runtime.session)
        current_goal = (snapshot.get("goals", {}) or {}).get(str(getattr(turn, "goal_id", None)), {})
        return {
            "assignment_id": assignment_id,
            "session_id": enrollment.session_id,
            "status": "running",
            "first_question": question.model_dump(mode="json") if hasattr(question, "model_dump") else question,
            "turn_index": getattr(turn, "index", None),
            "duration_seconds": runtime._duration_seconds(),
            "elapsed_seconds": runtime._elapsed_seconds(),
            "remaining_seconds": max(0.0, runtime._duration_seconds() - runtime._elapsed_seconds()),
            "current_goal_id": getattr(turn, "goal_id", None),
            "current_goal_budget_seconds": current_goal.get("budget_seconds"),
            "current_goal_elapsed_seconds": current_goal.get("elapsed_seconds"),
            "current_goal_remaining_seconds": current_goal.get("remaining_seconds"),
            "goal_time_snapshot": snapshot,
            **live,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/my/assignments/{assignment_id}/start", response_model=EnrollmentResponse)
def start_my_assignment(assignment_id: str, student: User = Depends(require_student), service=Depends(get_multiuser_service)):
    try:
        enrollment = service.mark_started(student=student, assignment_id=assignment_id)
        return _enrollment_response(enrollment)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
