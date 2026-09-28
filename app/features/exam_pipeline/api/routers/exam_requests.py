"""
app/api/routers/exam_requests.py

Controller for managing oral/adaptive exam requests directly from frontend inputs
(e.g., CreateExamAccordion, Teacher Dashboard, Student Exam View).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form

from ...api.dependencies import get_framework, get_goal_service, get_interview_service
from ...api.dependencies_multiuser import get_current_user, get_multiuser_service, require_professor, require_student
from ...api.schemas.exam_requests import (
    ExamCreateRequest,
    ExamUpdateRequest,
    ExamResponse,
    StudentExamCardResponse,
    ExamSlot,
    SlotRescheduleRequest,
    SlotListResponse,
    TeacherExamResultsResponse,
    TeacherStudentProgress,
    ExamSessionDetailResponse,
    TurnDetail,
    GoalMetricDetail,
    RecommendationDetail,
)
from ...api.schemas.goals import GoalResponse, IndicatorResponse
from ...api.schemas.interviews import InterviewConfigurationRequest
from ...goals.models import GoalModel
from ...multiuser.models import User, UserRole, AssignmentStudent, AssignmentStatus


router = APIRouter(
    prefix="/exams",
    tags=["Exam Requests & Frontend Management"],
)


def _parse_time_or_dt(val: Optional[Union[datetime, str]], base_date=None) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    val_str = str(val).strip()
    try:
        return datetime.fromisoformat(val_str)
    except Exception:
        pass
    try:
        t = datetime.strptime(val_str, "%H:%M").time()
        b_date = base_date or datetime.now().date()
        return datetime.combine(b_date, t)
    except Exception:
        return None


def _generate_time_slots(
    starts_at: Optional[datetime],
    ends_at: Optional[datetime],
    duration_minutes: int,
    gap_minutes: int = 5,
    student_slots: Optional[dict[str, dict]] = None,
    current_student_id: Optional[str] = None,
) -> tuple[str, str, list[ExamSlot]]:
    """
    Computes time slots within the starts_at -> ends_at window.
    Default fallback: 10:00 -> 14:00 if window is not set.
    """
    from datetime import timedelta, timezone
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    if starts_at and ends_at:
        if starts_at.tzinfo is not None:
            cur_dt = starts_at.astimezone(tehran_tz)
        else:
            cur_dt = starts_at
        if ends_at.tzinfo is not None:
            end_dt = ends_at.astimezone(tehran_tz)
        else:
            end_dt = ends_at

        w_start_str = cur_dt.strftime("%H:%M")
        w_end_str = end_dt.strftime("%H:%M")
    else:
        w_start_str = "10:00"
        w_end_str = "14:00"
        base_date = datetime.now().date()
        cur_dt = datetime.combine(base_date, datetime.strptime("10:00", "%H:%M").time())
        end_dt = datetime.combine(base_date, datetime.strptime("14:00", "%H:%M").time())

    slot_step = max(5, duration_minutes + (gap_minutes or 5))
    slots = []
    idx = 0
    student_slots = student_slots or {}

    # reverse lookup: slot_index -> student_id
    booked_slots = {}
    for sid, sdata in student_slots.items():
        if isinstance(sdata, dict) and "slot_index" in sdata:
            booked_slots[sdata["slot_index"]] = sid

    while cur_dt + timedelta(minutes=duration_minutes) <= end_dt:
        slot_start = cur_dt.strftime("%H:%M")
        slot_end = (cur_dt + timedelta(minutes=duration_minutes)).strftime("%H:%M")
        booked_by = booked_slots.get(idx)
        is_booked = booked_by is not None
        booked_by_me = (str(booked_by) == str(current_student_id)) if current_student_id else False

        slots.append(
            ExamSlot(
                slot_index=idx,
                start_time=slot_start,
                end_time=slot_end,
                is_booked=is_booked,
                booked_by_me=booked_by_me,
                student_id=str(booked_by) if booked_by else None,
            )
        )
        cur_dt += timedelta(minutes=slot_step)
        idx += 1

    return w_start_str, w_end_str, slots


def _to_goal_response(goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        bloom_level=goal.bloom_level,
        goal_type=goal.goal_type,
        importance=goal.importance,
        difficulty=goal.difficulty,
        estimated_questions=goal.estimated_questions,
        allocated_minutes=goal.allocated_minutes,
        allocated_seconds=goal.allocated_seconds,
        weight=goal.weight,
        indicators=[
            IndicatorResponse(
                id=ind.id,
                name=ind.name,
                indicator_type=ind.indicator_type,
                description=ind.description,
                required=ind.required,
                weight=ind.weight,
                difficulty=ind.difficulty,
            )
            for ind in goal.indicators
        ],
        status=goal.status,
    )


@router.post("/goals/generate-from-file")
async def generate_goals_from_file(
    file: UploadFile = File(...),
    course_title: Optional[str] = Form(None),
    exam_title: Optional[str] = Form(None),
    max_goals: int = Form(5),
    framework=Depends(get_framework),
):
    """
    Extracts text from an uploaded course document (PDF, DOCX, TXT, PPTX) and generates
    structured oral assessment goals (Bloom level, type, description) via LLM or fallback pipeline.
    """
    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="فایل ارسالی خالی است.")

    from ...knowledge.file_extractor import extract_text_from_file_bytes, optimize_content_for_llm
    raw_text = extract_text_from_file_bytes(file.filename, content_bytes, max_chars=40000)

    if not raw_text or len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="امکان استخراج متن از این فایل وجود ندارد یا فایل فاقد محتوای متنی است."
        )

    # Intelligently condense text to strictly <= 2000 chars (approx. 1000 - 1500 tokens)
    # This prevents HTTP 400 Context Length Exceeded errors on 4096-token LLM models
    optimized_text = optimize_content_for_llm(raw_text, filename=file.filename, max_chars=2000)

    goals = []
    # 1. Attempt LLM generation
    try:
        from ...llm.provider import LLMProvider
        from ...configuration.llm_configuration import LLMConfiguration
        import json
        import re

        llm = LLMProvider(configuration=LLMConfiguration.from_env())

        system_prompt = (
            "You are an expert university professor and oral examination designer.\n"
            "Analyze the following educational text/syllabus and extract the most important assessment goals (سرفصل‌ها و اهداف ارزیابی آزمون شفاهی).\n"
            f"Generate between 2 to {max_goals} distinct, high-quality goals in PERSIAN.\n"
            "Each goal must have:\n"
            "- title: Short, clear topic title in Persian (e.g., 'مفاهیم زمان‌بندی پردازنده و الگوریتم‌های آن')\n"
            "- description: Concise explanation of what is evaluated (in Persian)\n"
            "- goal_type: exactly one of ['theoretical', 'practical', 'analytical']\n"
            "- bloom_level: integer from 1 to 6 (1: یادآوری, 2: درک مفاهیم, 3: به‌کارگیری, 4: تحلیل, 5: ارزیابی, 6: آفرینش)\n\n"
            "Return ONLY a valid JSON array of objects. Do not include markdown code block backticks if possible, or wrap cleanly in ```json ... ```. No extra commentary."
        )

        user_content = (
            f"درس: {course_title or 'سیستم عامل'}\n"
            f"عنوان آزمون: {exam_title or 'آزمون شفاهی'}\n"
            f"تعداد اهداف مورد نیاز: {max_goals}\n\n"
            f"خلاصه و سرفصل‌های کلیدی استخراج‌شده از سند «{file.filename}»:\n\n"
            f"{optimized_text}"
        )

        def _parse_llm_json(raw_resp: str):
            cleaned = raw_resp.strip()
            if "```" in cleaned:
                m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(1)
                else:
                    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned).strip()
            return json.loads(cleaned)

        try:
            llm_response = llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ])
            parsed = _parse_llm_json(llm_response)
        except Exception as chat_err:
            err_str = str(chat_err)
            if "400" in err_str and ("context length" in err_str.lower() or "reduce the length" in err_str.lower() or "input tokens" in err_str.lower()):
                logging.getLogger(__name__).warning("Context length limit encountered (%s). Retrying with ultra-compact 800-char text...", chat_err)
                ultra_compact = optimized_text[:800].rsplit("\n", 1)[0]
                user_content_retry = (
                    f"درس: {course_title or 'سیستم عامل'}\n"
                    f"مباحث کلیدی:\n\n{ultra_compact}"
                )
                llm_response = llm.chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content_retry}
                ])
                parsed = _parse_llm_json(llm_response)
            else:
                raise chat_err

        if isinstance(parsed, list):
            valid_types = {"theoretical", "practical", "analytical"}
            type_mapping = {
                "knowledge": "theoretical",
                "understanding": "theoretical",
                "concept": "theoretical",
                "theory": "theoretical",
                "تئوری": "theoretical",
                "مفهومی": "theoretical",
                "application": "practical",
                "practical": "practical",
                "کاربردی": "practical",
                "عملی": "practical",
                "analysis": "analytical",
                "analytical": "analytical",
                "evaluation": "analytical",
                "تحلیلی": "analytical",
            }
            bloom_text_map = {
                "1": 1, "remember": 1, "یادآوری": 1, "حفظ": 1,
                "2": 2, "understand": 2, "comprehension": 2, "درک": 2, "درک مفاهیم": 2, "مفهومی": 2, "فهم": 2,
                "3": 3, "apply": 3, "application": 3, "به‌کارگیری": 3, "بکارگیری": 3, "کاربرد": 3, "عملی": 3,
                "4": 4, "analyze": 4, "analysis": 4, "تحلیل": 4, "تحلیلی": 4, "تحليلي": 4,
                "5": 5, "evaluate": 5, "evaluation": 5, "ارزیابی": 5, "تقييم": 5, "تقييمي": 5, "داوری": 5,
                "6": 6, "create": 6, "creation": 6, "synthesis": 6, "آفرینش": 6, "خلق": 6, "طراحی": 6,
            }

            for item in parsed[:max_goals]:
                if isinstance(item, dict):
                    t = item.get("title", "").strip()
                    if not t:
                        continue
                    gt_raw = str(item.get("goal_type", "theoretical")).lower().strip()
                    gt = type_mapping.get(gt_raw, "theoretical" if gt_raw not in valid_types else gt_raw)

                    raw_bl = str(item.get("bloom_level", 2)).strip().lower()
                    bl = bloom_text_map.get(raw_bl, 2)
                    if raw_bl.isdigit():
                        bl = max(1, min(6, int(raw_bl)))

                    goals.append({
                        "title": t,
                        "description": item.get("description", f"ارزیابی {t}"),
                        "goal_type": gt,
                        "bloom_level": bl,
                    })
    except Exception as exc:
        logging.getLogger(__name__).warning("LLM goal extraction failed: %s. Using KnowledgeProcessor fallback.", exc)

    # 2. Fallback to KnowledgeProcessor + GoalGenerator if LLM returned no goals
    if not goals:
        try:
            from ...knowledge.models import KnowledgeBase, Document
            from ...knowledge.processor import KnowledgeProcessor
            from ...goals.generator import GoalGenerator

            temp_kb = KnowledgeBase(id="temp_extract", title=file.filename)
            temp_kb.documents.append(Document(id="doc_1", filename=file.filename, content=optimized_text))
            graph = KnowledgeProcessor().process(temp_kb)
            goal_model = GoalGenerator().generate(graph=graph, max_goals=max_goals)

            for g in goal_model.goals:
                bloom_int = getattr(g.bloom_level, "value", 2) if hasattr(g.bloom_level, "value") else 2
                if isinstance(bloom_int, str):
                    bloom_map = {"remember": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 6}
                    bloom_int = bloom_map.get(bloom_int.lower(), 2)
                goals.append({
                    "title": g.title,
                    "description": g.description or f"ارزیابی {g.title}",
                    "goal_type": "theoretical",
                    "bloom_level": int(bloom_int),
                })
        except Exception as exc:
            logging.getLogger(__name__).warning("Fallback goal generation failed: %s", exc)

    if not goals:
        # Extract meaningful topics from headings in optimized_text if available
        candidate_lines = [
            re.sub(r"^[\d۰-۹\-•*.)]+\s*", "", l).strip()
            for l in optimized_text.splitlines()
            if 5 < len(l.strip()) < 80 and not any(bad in l for bad in ["<<", ">>", "obj", "stream"])
        ]
        if candidate_lines:
            for top_title in candidate_lines[:max_goals]:
                goals.append({
                    "title": top_title,
                    "description": f"ارزیابی و سنجش تسلط دانشجو بر مبحث {top_title}",
                    "goal_type": "theoretical",
                    "bloom_level": 2,
                })
        else:
            base_name = file.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
            goals = [
                {"title": f"مفاهیم پایه {base_name}", "description": f"آشنایی و درک مفاهیم کلیدی {base_name}", "goal_type": "theoretical", "bloom_level": 2},
                {"title": f"تحلیل و کاربرد {base_name}", "description": f"به‌کارگیری و تحلیل مسائل مربوط به {base_name}", "goal_type": "practical", "bloom_level": 3},
            ]

    return {
        "status": "success",
        "source_file": file.filename,
        "text_length": len(raw_text),
        "optimized_length": len(optimized_text),
        "goals": goals,
    }


@router.post("/create", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
def create_exam_request(
    request: ExamCreateRequest,
    current_user: User = Depends(require_professor),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Creates an adaptive exam from frontend input (e.g. CreateExamAccordion).
    Generates GoalModel, calibrates per-goal time budgets, provisions Assignment,
    enrolls students, and auto-publishes for launch.
    """
    total_seconds = request.duration_minutes * 60
    kb_id = f"kb_{request.course_id or request.lesson_id or 'default'}"

    # 1. Ensure KnowledgeBase exists in framework
    from ...knowledge.models import KnowledgeBase
    kb = framework.services.knowledge_service.get_knowledge_base(kb_id)
    if kb is None:
        kb = KnowledgeBase(
            id=kb_id,
            title=f"Knowledge Base: {request.title}",
            description=request.description or "",
        )
        framework.services.knowledge_service.save(kb)

    # 2. Build and persist GoalModel from user goals input
    goals_data = [g.model_dump() if hasattr(g, "model_dump") else g for g in request.goals]
    if not goals_data:
        # Fallback default goal if none provided
        goals_data = [f"مباحث کلی آزمون {request.title}"]

    goal_model = GoalModel.create_from_input(
        knowledge_base_id=kb_id,
        goals_data=goals_data,
        title=request.title,
        course_id=request.course_id,
        lesson_id=request.lesson_id,
        total_duration_minutes=request.duration_minutes,
    )

    framework.services.goal_service.save(goal_model)

    # 3. Calculate exact time allocations across active goals
    allocations = goal_model.calculate_time_allocations(total_seconds)

    # 4. Create MultiUser Assignment
    starts_dt = _parse_time_or_dt(request.start_at or request.starts_at)
    ends_dt = _parse_time_or_dt(request.end_at or request.ends_at)
    assignment = multiuser_service.create_assignment(
        professor=current_user,
        title=request.title,
        description=request.description or f"آزمون شفاهی {request.title}",
        knowledge_base_id=kb_id,
        goal_model_id=goal_model.id,
        duration_seconds=total_seconds,
        goal_time_allocations_seconds=allocations,
        passing_threshold=request.passing_threshold,
        allow_followup_questions=request.allow_followup_questions,
        starts_at=starts_dt,
        ends_at=ends_dt,
    )

    if assignment.configuration_snapshot is None:
        assignment.configuration_snapshot = {}
    assignment.configuration_snapshot["gap_minutes"] = request.gap_minutes or 5
    if request.materials:
        assignment.configuration_snapshot["materials"] = request.materials

    # 5. Ensure students exist in pipeline repository and enroll them
    cleaned_student_ids = [str(sid).strip() for sid in request.student_ids if str(sid).strip()]
    if cleaned_student_ids:
        from ...multiuser.models import User as PipelineUser, UserRole as PipelineUserRole
        for sid in cleaned_student_ids:
            existing_student = multiuser_service.repository.get_user(sid)
            if not existing_student or existing_student.role != PipelineUserRole.STUDENT:
                multiuser_service.repository.save_user(
                    PipelineUser(
                        id=sid,
                        email=f"{sid}@dt.internal",
                        display_name=f"Student {sid}",
                        password_hash="",
                        role=PipelineUserRole.STUDENT,
                    )
                )
        try:
            assignment = multiuser_service.enroll_students(
                professor=current_user,
                assignment_id=assignment.id,
                student_ids=cleaned_student_ids,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Enroll students warning: %s", exc)

        # Pre-assign initial time slots to enrolled students
        dur_mins = request.duration_minutes
        gap_mins = request.gap_minutes or 5
        _, _, init_slots = _generate_time_slots(
            assignment.starts_at,
            assignment.ends_at,
            duration_minutes=dur_mins,
            gap_minutes=gap_mins,
        )
        student_slots = {}
        for i, sid in enumerate(cleaned_student_ids):
            if i < len(init_slots):
                student_slots[sid] = {
                    "slot_index": init_slots[i].slot_index,
                    "start_time": init_slots[i].start_time,
                    "end_time": init_slots[i].end_time,
                }
        assignment.configuration_snapshot["student_slots"] = student_slots

    # 6. Auto-publish assignment
    assignment = multiuser_service.publish_assignment(
        professor=current_user,
        assignment_id=assignment.id,
    )

    return ExamResponse(
        quiz_id=assignment.id,
        id=assignment.id,
        assignment_id=assignment.id,
        goal_model_id=goal_model.id,
        title=assignment.title,
        description=assignment.description,
        course_id=request.course_id,
        lesson_id=request.lesson_id,
        duration_minutes=request.duration_minutes,
        duration_seconds=total_seconds,
        goal_count=len(goal_model.goals),
        goals=[_to_goal_response(g) for g in goal_model.goals],
        goal_time_allocations_seconds=allocations,
        student_count=len(assignment.students),
        student_ids=cleaned_student_ids,
        gap_minutes=request.gap_minutes,
        exam_date=request.exam_date,
        start_at=request.start_at,
        end_at=request.end_at,
        status=assignment.status.value,
        is_active=request.is_active if request.is_active is not None else True,
        created_at=datetime.utcnow(),
    )


@router.get("", response_model=list[ExamResponse])
def list_exams(
    current_user: User = Depends(require_professor),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    List all exams created by the professor with their goals and student rosters.
    """
    assignments = multiuser_service.professor_assignments(professor=current_user)
    result = []
    for a in assignments:
        goal_model = framework.get_goal_model(a.goal_model_id)
        goals_resp = [_to_goal_response(g) for g in goal_model.goals] if goal_model else []
        result.append(
            ExamResponse(
                quiz_id=a.id,
                id=a.id,
                assignment_id=a.id,
                goal_model_id=a.goal_model_id,
                title=a.title,
                description=a.description,
                duration_minutes=a.duration_seconds // 60,
                duration_seconds=a.duration_seconds,
                goal_count=len(goals_resp),
                goals=goals_resp,
                goal_time_allocations_seconds=a.goal_time_allocations_seconds or {},
                student_count=len(a.students),
                student_ids=list(a.students.keys()),
                status=a.status.value,
                start_at=a.starts_at,
                end_at=a.ends_at,
                starts_at=a.starts_at,
                ends_at=a.ends_at,
                created_at=datetime.utcnow(),
            )
        )
    return result


async def _sync_db_quizzes_to_pipeline(multiuser_service, framework, student_id_str: str | None = None):
    try:
        from app.core.database import async_session
        from app.features.users.models import User as DBUser
        from app.features.chat.models import Chat, ChatMember, Message
        from app.features.bot.models import BotConfig
        from app.features.auth.models import UserSession
        from app.features.lessons.models import QuizAttempt, QuizQuestion, LessonMaterial, Lesson, LessonMember, LessonBotChat, LessonQuiz
        from sqlalchemy import select
        import uuid

        async with async_session() as session:
            lesson_ids = []
            if student_id_str:
                try:
                    u_uuid = uuid.UUID(student_id_str)
                    stmt_m = select(LessonMember.lesson_id).where(LessonMember.user_id == u_uuid)
                    res_m = await session.execute(stmt_m)
                    lesson_ids = [row[0] for row in res_m.fetchall()]
                except Exception:
                    pass

            default_lid = uuid.UUID("c0000000-0000-4000-8000-000000000001")
            if default_lid not in lesson_ids:
                lesson_ids.append(default_lid)

            stmt_q = select(LessonQuiz).where(LessonQuiz.lesson_id.in_(lesson_ids), LessonQuiz.is_active == True)
            res_q = await session.execute(stmt_q)
            db_quizzes = res_q.scalars().all()

            from app.features.exam_pipeline.knowledge.models import KnowledgeBase

            for q in db_quizzes:
                qid = str(q.quiz_id)
                assignment = multiuser_service.repository.get_assignment(qid)
                if not assignment:
                    kb_id = f"kb_{q.lesson_id}"
                    kb = framework.services.knowledge_service.get_knowledge_base(kb_id)
                    if not kb:
                        kb = KnowledgeBase(
                            id=kb_id,
                            title=f"Knowledge Base: {q.title}",
                            description=q.description or "",
                        )
                        framework.services.knowledge_service.save(kb)

                    goals_list = q.goals or [f"مباحث آزمون {q.title}"]
                    dur_mins = q.duration_minutes or 20
                    goal_model = GoalModel.create_from_input(
                        knowledge_base_id=kb_id,
                        goals_data=goals_list,
                        title=q.title,
                        course_id=str(q.lesson_id),
                        lesson_id=str(q.lesson_id),
                        total_duration_minutes=dur_mins,
                    )
                    framework.services.goal_service.save(goal_model)
                    allocations = goal_model.calculate_time_allocations(dur_mins * 60)

                    prof_id = str(q.teacher_id or "10000000-0000-4000-8000-000000000001")
                    prof = multiuser_service.repository.get_user(prof_id)
                    if not prof:
                        prof = User(
                            id=prof_id,
                            email="teacher@dt.internal",
                            display_name="Teacher",
                            password_hash="",
                            role=UserRole.PROFESSOR,
                        )
                        multiuser_service.repository.save_user(prof)

                    assignment = multiuser_service.create_assignment(
                        professor=prof,
                        title=q.title,
                        description=q.description or f"آزمون درس {q.title}",
                        knowledge_base_id=kb_id,
                        goal_model_id=goal_model.id,
                        duration_seconds=dur_mins * 60,
                        goal_time_allocations_seconds=allocations,
                        passing_threshold=0.70,
                        allow_followup_questions=True,
                        starts_at=q.start_at,
                        ends_at=q.end_at,
                        assignment_id=qid,
                    )
                    assignment.status = AssignmentStatus.PUBLISHED
                    multiuser_service.repository.save_assignment(assignment)

                    s_ids = [str(s).strip() for s in (q.student_ids or []) if str(s).strip()]
                    if s_ids:
                        for s_id in s_ids:
                            if not multiuser_service.repository.get_user(s_id):
                                multiuser_service.repository.save_user(
                                    User(
                                        id=s_id,
                                        email=f"{s_id}@dt.internal",
                                        display_name=f"Student {s_id}",
                                        password_hash="",
                                        role=UserRole.STUDENT,
                                    )
                                )
                        try:
                            assignment = multiuser_service.enroll_students(
                                professor=prof,
                                assignment_id=assignment.id,
                                student_ids=s_ids,
                            )
                        except Exception as exc:
                            logging.getLogger(__name__).warning("Enroll students during sync warning: %s", exc)

                        _, _, init_slots = _generate_time_slots(
                            assignment.starts_at,
                            assignment.ends_at,
                            duration_minutes=dur_mins,
                            gap_minutes=q.gap_minutes or 5,
                        )
                        student_slots = {}
                        for i, sid in enumerate(s_ids):
                            if i < len(init_slots):
                                student_slots[sid] = {
                                    "slot_index": init_slots[i].slot_index,
                                    "start_time": init_slots[i].start_time,
                                    "end_time": init_slots[i].end_time,
                                }
                        if assignment.configuration_snapshot is None:
                            assignment.configuration_snapshot = {}
                        assignment.configuration_snapshot["student_slots"] = student_slots
                        assignment.configuration_snapshot["gap_minutes"] = q.gap_minutes or 5
                        multiuser_service.repository.save_assignment(assignment)
    except Exception as exc:
        logging.getLogger(__name__).warning("Error syncing DB quizzes to pipeline: %s", exc)


@router.get("/my-exams", response_model=list[StudentExamCardResponse])
async def my_student_exams(
    student: User = Depends(require_student),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    List exams assigned to the current logged-in student.
    Auto-enrolls student in published course assignments if not already enrolled.
    """
    # 1. Ensure student user is registered in pipeline repository
    if not multiuser_service.repository.get_user(student.id):
        multiuser_service.repository.save_user(student)

    # 2. Sync any persistent quizzes from DB into in-memory pipeline
    await _sync_db_quizzes_to_pipeline(multiuser_service, framework, student_id_str=student.id)

    # 3. Check all published assignments; if student is not yet enrolled, auto-enroll them
    all_assignments = multiuser_service.repository.list_assignments()
    for assignment in all_assignments:
        if assignment.status == AssignmentStatus.PUBLISHED:
            if student.id not in assignment.students:
                try:
                    config = InterviewConfigurationRequest.model_validate(assignment.configuration_snapshot)
                    session = multiuser_service.interview_service.create_session(
                        student_id=student.id,
                        knowledge_model=copy.deepcopy(assignment.knowledge_snapshot),
                        goal_model=copy.deepcopy(assignment.goal_model_snapshot),
                        configuration=config,
                        interviewer_id=assignment.professor_id,
                    )
                    session.metadata.update({
                        "multi_user_version": multiuser_service.VERSION,
                        "assignment_id": assignment.id,
                        "opening_question_variant": len(assignment.students),
                        "professor_id": assignment.professor_id,
                        "student_id": student.id,
                        "assignment_snapshot": {
                            "knowledge_base_id": assignment.knowledge_base_id,
                            "goal_model_id": assignment.goal_model_id,
                            "configuration": copy.deepcopy(assignment.configuration_snapshot),
                        },
                    })
                    multiuser_service.interview_service.save(session)
                    assignment.students[student.id] = AssignmentStudent(
                        assignment_id=assignment.id,
                        student_id=student.id,
                        session_id=session.id,
                    )
                    multiuser_service.repository.save_assignment(assignment)
                except Exception as exc:
                    logging.getLogger(__name__).warning("Auto-enrollment error for student %s: %s", student.id, exc)

    pairs = multiuser_service.student_assignments(student=student)
    cards = []
    seen_assignment_ids = set()
    for assignment, enrollment in pairs:
        if assignment.id in seen_assignment_ids:
            continue
        seen_assignment_ids.add(assignment.id)
        multiuser_service.sync_enrollment_status(assignment=assignment, enrollment=enrollment)
        goal_model = framework.get_goal_model(assignment.goal_model_id)
        topic = "، ".join([g.title for g in goal_model.goals[:3]]) if goal_model else assignment.title

        score = None
        passed = None
        if enrollment.session_id:
            try:
                session = multiuser_service.interview_service.get_session(enrollment.session_id)
                if session and getattr(session, "completed", False):
                    res = framework.build_result(enrollment.session_id)
                    score = getattr(res, "score", None)
                    passed = getattr(res, "passed", None)
            except Exception:
                pass

        # Calculate student's scheduled time slot
        config_snapshot = assignment.configuration_snapshot or {}
        student_slots = config_snapshot.setdefault("student_slots", {})
        gap_mins = config_snapshot.get("gap_minutes", 5)
        dur_mins = assignment.duration_seconds // 60

        w_start, w_end, slots = _generate_time_slots(
            assignment.starts_at,
            assignment.ends_at,
            duration_minutes=dur_mins,
            gap_minutes=gap_mins,
            student_slots=student_slots,
            current_student_id=student.id,
        )

        # If student doesn't have an assigned slot yet, assign first open slot
        if student.id not in student_slots and slots:
            for s in slots:
                if not s.is_booked:
                    student_slots[student.id] = {
                        "slot_index": s.slot_index,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                    }
                    s.is_booked = True
                    s.booked_by_me = True
                    s.student_id = student.id
                    multiuser_service.repository.save_assignment(assignment)
                    break

        my_slot = student_slots.get(student.id)
        from ...multiuser.models import EnrollmentStatus
        if enrollment.status == EnrollmentStatus.ASSIGNED and my_slot:
            e_str = my_slot.get("end_time")
            if e_str and ":" in e_str:
                eh, em = map(int, e_str.split(":"))
                slot_end_mins = eh * 60 + em
                from datetime import datetime, timezone, timedelta
                tehran_tz = timezone(timedelta(hours=3, minutes=30))
                now_tehran = datetime.now(timezone.utc).astimezone(tehran_tz)
                cur_mins = now_tehran.hour * 60 + now_tehran.minute
                overall_end_mins = 24 * 60
                if assignment.ends_at:
                    end_dt = assignment.ends_at.astimezone(tehran_tz) if assignment.ends_at.tzinfo else assignment.ends_at
                    overall_end_mins = end_dt.hour * 60 + end_dt.minute
                if cur_mins > slot_end_mins and cur_mins <= overall_end_mins:
                    found_slot = None
                    for sl in slots:
                        ssh, ssm = map(int, sl.start_time.split(":"))
                        seh, sem = map(int, sl.end_time.split(":"))
                        smins = ssh * 60 + ssm
                        emins = seh * 60 + sem
                        if smins - 2 <= cur_mins <= emins and (not sl.is_booked or sl.booked_by_me):
                            found_slot = sl
                            break
                    if not found_slot:
                        for sl in slots:
                            seh, sem = map(int, sl.end_time.split(":"))
                            emins = seh * 60 + sem
                            if cur_mins <= emins and (not sl.is_booked or sl.booked_by_me):
                                found_slot = sl
                                break
                    if found_slot:
                        student_slots[student.id] = {
                            "slot_index": found_slot.slot_index,
                            "start_time": found_slot.start_time,
                            "end_time": found_slot.end_time,
                        }
                        my_slot = student_slots[student.id]
                        multiuser_service.repository.save_assignment(assignment)

        student_slot_start = my_slot["start_time"] if my_slot else (slots[0].start_time if slots else w_start)
        student_slot_end = my_slot["end_time"] if my_slot else (slots[0].end_time if slots else w_end)

        cards.append(
            StudentExamCardResponse(
                id=assignment.id,
                assignment_id=assignment.id,
                session_id=enrollment.session_id,
                title=assignment.title,
                course="سیستم عامل",
                topic=topic,
                date=assignment.starts_at.strftime("%Y/%m/%d") if assignment.starts_at else "1405/07/20",
                start_at=assignment.starts_at.isoformat() if assignment.starts_at else None,
                end_at=assignment.ends_at.isoformat() if assignment.ends_at else None,
                duration=assignment.duration_seconds // 60,
                status=enrollment.status.value,
                score=score,
                passed=passed,
                window_start=w_start,
                window_end=w_end,
                student_slot_start=student_slot_start,
                student_slot_end=student_slot_end,
                gap_minutes=gap_mins,
            )
        )
    return cards


@router.get("/{assignment_id}/slots", response_model=SlotListResponse)
def get_exam_slots(
    assignment_id: str,
    current_user: User = Depends(get_current_user),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Returns the time slots for an exam, indicating which are available and which is booked by the current student.
    """
    assignment = multiuser_service.repository.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Exam assignment not found")

    config_snapshot = assignment.configuration_snapshot or {}
    student_slots = config_snapshot.setdefault("student_slots", {})
    gap_mins = config_snapshot.get("gap_minutes", 5)
    dur_mins = assignment.duration_seconds // 60

    w_start, w_end, slots = _generate_time_slots(
        assignment.starts_at,
        assignment.ends_at,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
        student_slots=student_slots,
        current_student_id=current_user.id,
    )

    my_slot_data = student_slots.get(current_user.id)
    my_slot = None
    if my_slot_data:
        my_slot = ExamSlot(
            slot_index=my_slot_data["slot_index"],
            start_time=my_slot_data["start_time"],
            end_time=my_slot_data["end_time"],
            is_booked=True,
            booked_by_me=True,
            student_id=current_user.id,
        )

    date_str = assignment.starts_at.strftime("%Y/%m/%d") if assignment.starts_at else "1405/07/20"

    return SlotListResponse(
        assignment_id=assignment.id,
        title=assignment.title,
        course="سیستم عامل",
        exam_date=date_str,
        window_start=w_start,
        window_end=w_end,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
        my_slot=my_slot,
        slots=slots,
    )


@router.post("/{assignment_id}/reschedule-slot", response_model=SlotListResponse)
def reschedule_exam_slot(
    assignment_id: str,
    req: SlotRescheduleRequest,
    student: User = Depends(require_student),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Allows a student to choose or move their booked slot to an open slot.
    """
    assignment = multiuser_service.repository.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Exam assignment not found")

    from ...multiuser.models import EnrollmentStatus
    enrollment = assignment.students.get(str(student.id))
    if enrollment and enrollment.status != EnrollmentStatus.ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="پس از شروع یا اتمام آزمون، امکان تغییر نوبت وجود ندارد.",
        )

    config_snapshot = assignment.configuration_snapshot or {}
    student_slots = config_snapshot.setdefault("student_slots", {})
    gap_mins = config_snapshot.get("gap_minutes", 5)
    dur_mins = assignment.duration_seconds // 60

    # Check if the requested slot is already taken by another student
    for sid, sdata in student_slots.items():
        if str(sid) != str(student.id) and sdata.get("slot_index") == req.slot_index:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="این نوبت زمانی توسط دانشجوی دیگری رزرو شده است. لطفاً زمان خالی دیگری را انتخاب کنید.",
            )

    # Assign new slot to current student
    student_slots[str(student.id)] = {
        "slot_index": req.slot_index,
        "start_time": req.start_time,
        "end_time": req.end_time,
    }
    assignment.configuration_snapshot = config_snapshot
    multiuser_service.repository.save_assignment(assignment)

    w_start, w_end, slots = _generate_time_slots(
        assignment.starts_at,
        assignment.ends_at,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
        student_slots=student_slots,
        current_student_id=student.id,
    )

    my_slot = ExamSlot(
        slot_index=req.slot_index,
        start_time=req.start_time,
        end_time=req.end_time,
        is_booked=True,
        booked_by_me=True,
        student_id=str(student.id),
    )

    date_str = assignment.starts_at.strftime("%Y/%m/%d") if assignment.starts_at else "1405/07/20"

    return SlotListResponse(
        assignment_id=assignment.id,
        title=assignment.title,
        course="سیستم عامل",
        exam_date=date_str,
        window_start=w_start,
        window_end=w_end,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
        my_slot=my_slot,
        slots=slots,
    )


@router.get("/{assignment_id}/results", response_model=TeacherExamResultsResponse)
async def get_teacher_exam_results(
    assignment_id: str,
    current_user: User = Depends(require_professor),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Returns aggregated exam results and student roster for the professor.
    """
    assignment = multiuser_service.repository.get_assignment(assignment_id)
    if not assignment:
        await _sync_db_quizzes_to_pipeline(multiuser_service, framework)
        assignment = multiuser_service.repository.get_assignment(assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Exam assignment not found")

    config_snapshot = assignment.configuration_snapshot or {}
    student_slots = config_snapshot.get("student_slots", {})
    gap_mins = config_snapshot.get("gap_minutes", 5)
    dur_mins = assignment.duration_seconds // 60

    w_start, w_end, _ = _generate_time_slots(
        assignment.starts_at,
        assignment.ends_at,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
    )

    # Fetch real user profiles from database if available
    user_map = {}
    try:
        from app.core.database import async_session
        from app.features.users.models import User as DBUser
        from sqlalchemy import select
        import uuid

        async with async_session() as session:
            student_id_strs = list(assignment.students.keys())
            uuids = []
            for sid in student_id_strs:
                try:
                    uuids.append(uuid.UUID(sid))
                except Exception:
                    pass
            if uuids:
                stmt = select(DBUser).where(DBUser.user_id.in_(uuids))
                res = await session.execute(stmt)
                for u in res.scalars().all():
                    full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username
                    user_map[str(u.user_id)] = {
                        "name": full_name,
                        "username": u.username,
                        "profile_url": u.profile_url,
                    }
    except Exception as e:
        logging.getLogger(__name__).warning("Error fetching student details: %s", e)

    students_list = []
    scores_list = []
    passed_count = 0

    for sid, enrollment in assignment.students.items():
        user_info = user_map.get(sid, {})
        u_fallback = multiuser_service.repository.get_user(sid)
        student_name = (
            user_info.get("name")
            or (u_fallback.display_name if u_fallback else None)
            or f"دانشجو {sid[:8]}"
        )
        username = user_info.get("username") or (u_fallback.email if u_fallback else sid)
        profile_url = user_info.get("profile_url")

        slot_info = student_slots.get(sid, {})
        slot_start = slot_info.get("start_time")
        slot_end = slot_info.get("end_time")

        score = None
        passed = None
        turns_count = 0
        status_val = enrollment.status.value if hasattr(enrollment.status, "value") else str(enrollment.status)

        if enrollment.session_id:
            try:
                session = multiuser_service.interview_service.get_session(enrollment.session_id)
                if session:
                    turns = getattr(getattr(session, "history", None), "turns", []) or getattr(session, "turns", []) or []
                    turns_count = len([t for t in turns if getattr(t, "has_question", True) or getattr(t, "question", "")])
                    if getattr(session, "completed", False):
                        status_val = "completed"
                        res = framework.build_result(enrollment.session_id)
                        score = getattr(res, "score", None)
                        if score is None and hasattr(res, "overall_mastery"):
                            score = round(res.overall_mastery * 100, 1)
                        passed = getattr(res, "passed", None)
            except Exception as e:
                logging.getLogger(__name__).warning("Error getting session for results: %s", e)

        if score is not None:
            scores_list.append(score)
            if passed:
                passed_count += 1

        students_list.append(
            TeacherStudentProgress(
                student_id=sid,
                student_name=student_name,
                username=username,
                profile_url=profile_url,
                status=status_val,
                score=score,
                passed=passed,
                slot_start=slot_start,
                slot_end=slot_end,
                session_id=enrollment.session_id,
                turns_count=turns_count,
            )
        )

    total_students = len(students_list)
    completed_students = sum(1 for s in students_list if s.status == "completed" or s.score is not None)
    average_score = round(sum(scores_list) / len(scores_list), 1) if scores_list else None
    pass_rate = round((passed_count / completed_students) * 100, 1) if completed_students > 0 else None
    date_str = assignment.starts_at.strftime("%Y/%m/%d") if assignment.starts_at else "1405/07/20"

    return TeacherExamResultsResponse(
        assignment_id=assignment.id,
        title=assignment.title,
        course="سیستم عامل",
        date=date_str,
        window_start=w_start,
        window_end=w_end,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
        total_students=total_students,
        completed_students=completed_students,
        average_score=average_score,
        pass_rate=pass_rate,
        students=students_list,
    )


@router.get("/{assignment_id}/sessions/{session_id}/detail", response_model=ExamSessionDetailResponse)
async def get_exam_session_detail(
    assignment_id: str,
    session_id: str,
    current_user: User = Depends(get_current_user),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Returns the comprehensive student exam report, score breakdown, AI recommendations,
    and the complete question/answer/feedback dialogue turns.
    Accessible by student participant and professor.
    """
    assignment = multiuser_service.repository.get_assignment(assignment_id)
    session = multiuser_service.interview_service.get_session(session_id)
    if not session:
        try:
            session = framework.get_session(session_id)
        except Exception:
            pass

    if not session:
        raise HTTPException(status_code=404, detail="Exam session not found")

    # Authorization check: only the student who took it or professors can view
    if current_user.role == UserRole.STUDENT and str(session.student_id) != str(current_user.id):
        if assignment and str(current_user.id) in assignment.students:
            enr = assignment.students[str(current_user.id)]
            if enr.session_id != session_id:
                raise HTTPException(status_code=403, detail="Access denied to this session report")
        else:
            raise HTTPException(status_code=403, detail="Access denied to this session report")

    student_name = None
    try:
        from app.core.database import async_session
        from app.features.users.models import User as DBUser
        from sqlalchemy import select
        import uuid

        async with async_session() as db_session:
            u_uuid = uuid.UUID(str(session.student_id))
            stmt = select(DBUser).where(DBUser.user_id == u_uuid)
            res = await db_session.execute(stmt)
            db_user = res.scalar_one_or_none()
            if db_user:
                student_name = f"{db_user.first_name or ''} {db_user.last_name or ''}".strip() or db_user.username
    except Exception:
        pass

    if not student_name:
        u_fallback = multiuser_service.repository.get_user(str(session.student_id))
        student_name = u_fallback.display_name if u_fallback else f"دانشجو {str(session.student_id)[:8]}"

    # Goal title mapping
    goal_map = {}
    if assignment:
        gm = framework.get_goal_model(assignment.goal_model_id)
        if gm:
            goal_map = {g.id: g.title for g in gm.goals}

    # Turns
    turns_list = []
    raw_turns = getattr(getattr(session, "history", None), "turns", []) or getattr(session, "turns", []) or []
    for i, t in enumerate(raw_turns):
        q_text = getattr(t, "question", "") or ""
        a_text = getattr(t, "answer", "") or ""
        meta = getattr(t, "metadata", {}) or {}
        asmt = meta.get("assessment", {}) if isinstance(meta, dict) else {}
        fb_text = getattr(t, "feedback", None) or (asmt.get("feedback") if isinstance(asmt, dict) else None)
        if not fb_text and isinstance(meta, dict):
            fb_text = meta.get("feedback")

        g_id = getattr(t, "goal_id", None)
        g_title = goal_map.get(g_id) if g_id else None

        ts = getattr(t, "timestamp", None)
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None

        decision = getattr(t, "decision", None)
        bloom = None
        if isinstance(decision, dict):
            bloom = decision.get("bloom_level")
        elif hasattr(decision, "bloom_level"):
            bloom = getattr(decision, "bloom_level", None)
        if not bloom and isinstance(asmt, dict):
            bloom = asmt.get("bloom_level")

        if q_text:
            turns_list.append(
                TurnDetail(
                    index=i + 1,
                    question=q_text,
                    answer=a_text,
                    feedback=fb_text,
                    goal_id=g_id,
                    goal_title=g_title,
                    timestamp=ts_str,
                    bloom_level=bloom,
                )
            )

    # Score, metrics & recommendations
    score = None
    passed = None
    overall_mastery = None
    overall_coverage = None
    overall_confidence = None
    goals_detail = []
    recommendations_detail = []

    try:
        report = framework.build_report(session_id)
        if report and hasattr(report, "metrics"):
            m = report.metrics
            overall_mastery = getattr(m, "overall_score", 0.0)
            score = round(overall_mastery * 100, 1)
            overall_coverage = getattr(m, "overall_coverage", 0.0)
            overall_confidence = getattr(m, "overall_confidence", 0.0)
            passed = getattr(m, "completed", True) and score >= 60.0

            for gm in getattr(m, "goal_metrics", []):
                goals_detail.append(
                    GoalMetricDetail(
                        goal_id=gm.goal_id,
                        title=gm.title,
                        score=round(gm.score * 100, 1) if gm.score <= 1.0 else gm.score,
                        coverage=round(gm.coverage * 100, 1) if gm.coverage <= 1.0 else gm.coverage,
                        mastery=round(gm.mastery * 100, 1) if gm.mastery <= 1.0 else gm.mastery,
                        confidence=round(gm.confidence * 100, 1) if gm.confidence <= 1.0 else gm.confidence,
                        completed=gm.completed,
                    )
                )

            for rec in getattr(report, "recommendations", []):
                recommendations_detail.append(
                    RecommendationDetail(
                        priority=rec.priority,
                        category=rec.category,
                        title=rec.title,
                        description=rec.description,
                        action=rec.action,
                    )
                )
    except Exception as e:
        logging.getLogger(__name__).warning("Build report fallback: %s", e)

    if score is None:
        try:
            res = framework.build_result(session_id)
            if res:
                overall_mastery = getattr(res, "overall_mastery", 0.0)
                score = round(overall_mastery * 100, 1)
                overall_coverage = getattr(res, "overall_coverage", 0.0)
                overall_confidence = getattr(res, "overall_confidence", 0.0)
                passed = getattr(res, "passed", True)

                for g in getattr(res, "goals", []):
                    goals_detail.append(
                        GoalMetricDetail(
                            goal_id=g.goal_id,
                            title=g.title,
                            score=round(g.mastery * 100, 1),
                            coverage=round(g.coverage * 100, 1),
                            mastery=round(g.mastery * 100, 1),
                            confidence=round(g.confidence * 100, 1),
                            completed=g.completed,
                        )
                    )
        except Exception:
            pass

    started_at = getattr(session, "started_at", None)
    finished_at = getattr(session, "finished_at", None)
    dur_sec = 0
    if started_at and finished_at:
        try:
            dur_sec = int((finished_at - started_at).total_seconds())
        except Exception:
            dur_sec = 0
    elif assignment:
        dur_sec = assignment.duration_seconds

    title = assignment.title if assignment else "آزمون شفاهی"

    return ExamSessionDetailResponse(
        session_id=session.id,
        assignment_id=assignment.id if assignment else "",
        student_id=str(session.student_id),
        student_name=student_name,
        exam_title=title,
        course="سیستم عامل",
        score=score,
        passed=passed,
        overall_mastery=overall_mastery,
        overall_coverage=overall_coverage,
        overall_confidence=overall_confidence,
        completed=getattr(session, "completed", False),
        started_at=started_at.isoformat() if started_at else None,
        finished_at=finished_at.isoformat() if finished_at else None,
        duration_seconds=dur_sec,
        turns=turns_list,
        goals=goals_detail,
        recommendations=recommendations_detail,
    )


@router.put("/{assignment_id}", response_model=ExamResponse)
async def update_exam(
    assignment_id: str,
    req: ExamUpdateRequest,
    current_user: User = Depends(require_professor),
    framework=Depends(get_framework),
    multiuser_service=Depends(get_multiuser_service),
):
    """
    Updates an exam assignment (title, timings, duration, goals, active status)
    and syncs both the pipeline repository and the PostgreSQL database.
    """
    assignment = multiuser_service.repository.get_assignment(assignment_id)
    if not assignment:
        await _sync_db_quizzes_to_pipeline(multiuser_service, framework)
        assignment = multiuser_service.repository.get_assignment(assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Exam assignment not found")

    if req.title:
        assignment.title = req.title
    if req.description is not None:
        assignment.description = req.description

    # Timings
    if req.start_at or req.starts_at:
        assignment.starts_at = _parse_time_or_dt(req.start_at or req.starts_at)
    if req.end_at or req.ends_at:
        assignment.ends_at = _parse_time_or_dt(req.end_at or req.ends_at)
    if req.duration_minutes:
        assignment.duration_seconds = req.duration_minutes * 60

    if assignment.configuration_snapshot is None:
        assignment.configuration_snapshot = {}
    if req.gap_minutes is not None:
        assignment.configuration_snapshot["gap_minutes"] = req.gap_minutes

    # Goals
    goals_data = None
    if req.goals is not None:
        goals_data = [g.model_dump() if hasattr(g, "model_dump") else g for g in req.goals]
        if not goals_data:
            goals_data = [f"مباحث کلی آزمون {assignment.title}"]
        kb_id = assignment.knowledge_base_id or f"kb_default"
        new_gm = GoalModel.create_from_input(
            knowledge_base_id=kb_id,
            goals_data=goals_data,
            title=assignment.title,
            total_duration_minutes=assignment.duration_seconds // 60,
        )
        new_gm.id = assignment.goal_model_id
        framework.services.goal_service.save(new_gm)
        assignment.goal_time_allocations_seconds = new_gm.calculate_time_allocations(assignment.duration_seconds)

    # Recalculate time slots
    dur_mins = assignment.duration_seconds // 60
    gap_mins = assignment.configuration_snapshot.get("gap_minutes", 5)
    _, _, new_slots = _generate_time_slots(
        assignment.starts_at,
        assignment.ends_at,
        duration_minutes=dur_mins,
        gap_minutes=gap_mins,
    )
    student_slots = assignment.configuration_snapshot.setdefault("student_slots", {})
    new_student_slots = {}
    for i, sid in enumerate(assignment.students.keys()):
        if i < len(new_slots):
            new_student_slots[sid] = {
                "slot_index": new_slots[i].slot_index,
                "start_time": new_slots[i].start_time,
                "end_time": new_slots[i].end_time,
            }
    assignment.configuration_snapshot["student_slots"] = new_student_slots

    # Active status
    if req.is_active is not None:
        assignment.status = AssignmentStatus.PUBLISHED if req.is_active else AssignmentStatus.CLOSED

    multiuser_service.repository.save_assignment(assignment)

    # Sync to DB
    try:
        from app.core.database import async_session
        from app.features.lessons.models import LessonQuiz
        from sqlalchemy import select
        import uuid

        async with async_session() as session:
            try:
                q_uuid = uuid.UUID(assignment_id)
                stmt = select(LessonQuiz).where(LessonQuiz.quiz_id == q_uuid)
                res = await session.execute(stmt)
                db_quiz = res.scalar_one_or_none()
                if db_quiz:
                    if req.title:
                        db_quiz.title = req.title
                    if req.description is not None:
                        db_quiz.description = req.description
                    if req.duration_minutes:
                        db_quiz.duration_minutes = req.duration_minutes
                    if req.gap_minutes is not None:
                        db_quiz.gap_minutes = req.gap_minutes
                    if req.exam_date:
                        db_quiz.exam_date = req.exam_date
                    if assignment.starts_at:
                        db_quiz.start_at = assignment.starts_at
                    if assignment.ends_at:
                        db_quiz.end_at = assignment.ends_at
                    if goals_data is not None:
                        db_quiz.goals = goals_data
                    if req.is_active is not None:
                        db_quiz.is_active = req.is_active
                    await session.commit()
            except ValueError:
                pass
    except Exception as e:
        logging.getLogger(__name__).warning("Error syncing exam edit to LessonQuiz: %s", e)

    goal_model = framework.get_goal_model(assignment.goal_model_id)
    goals_resp = [_to_goal_response(g) for g in goal_model.goals] if goal_model else []

    date_str = assignment.starts_at.strftime("%Y/%m/%d") if assignment.starts_at else "1405/07/20"

    return ExamResponse(
        quiz_id=assignment.id,
        id=assignment.id,
        assignment_id=assignment.id,
        goal_model_id=assignment.goal_model_id,
        title=assignment.title,
        description=assignment.description,
        duration_minutes=assignment.duration_seconds // 60,
        duration_seconds=assignment.duration_seconds,
        goal_count=len(goals_resp),
        goals=goals_resp,
        goal_time_allocations_seconds=assignment.goal_time_allocations_seconds or {},
        student_count=len(assignment.students),
        student_ids=list(assignment.students.keys()),
        gap_minutes=gap_mins,
        exam_date=date_str,
        start_at=assignment.starts_at.isoformat() if assignment.starts_at else None,
        end_at=assignment.ends_at.isoformat() if assignment.ends_at else None,
        starts_at=assignment.starts_at.isoformat() if assignment.starts_at else None,
        ends_at=assignment.ends_at.isoformat() if assignment.ends_at else None,
        status=assignment.status.value,
        is_active=assignment.status == AssignmentStatus.PUBLISHED,
        created_at=datetime.utcnow(),
    )

