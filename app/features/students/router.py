from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.features.users.models import User
from app.features.lessons.models import LessonMember
from app.features.chat.models import Message
from app.features.auth.models import UserSession
from .schemas import StudentResponse, BlockStudentRequest

router = APIRouter()

def _compute_session_status(session: Optional[UserSession], user: User) -> tuple[str, str, str, bool, Optional[str]]:
    now = datetime.now(timezone.utc)
    last_active = None
    is_online = False

    if session and session.last_active_at:
        last_active = session.last_active_at
        if session.revoked_at is None and (session.expires_at is None or session.expires_at > now):
            elapsed_sec = (now - session.last_active_at).total_seconds()
            if elapsed_sec <= 300:  # 5 minutes threshold
                is_online = True
    elif hasattr(user, "updated_at") and user.updated_at:
        last_active = user.updated_at
    elif hasattr(user, "created_at") and user.created_at:
        last_active = user.created_at

    dt_str = last_active.isoformat() if last_active else None

    if is_online:
        return "online", "آنلاین", "Online", True, dt_str

    if not last_active:
        return "offline", "اخیراً آنلاین بوده", "Last seen recently", False, None

    diff_sec = max(0, (now - last_active).total_seconds())

    if diff_sec < 60:
        return "offline", "چند لحظه پیش آنلاین بوده", "Last seen just now", False, dt_str
    elif diff_sec < 3600:
        mins = max(1, int(diff_sec / 60))
        return f"Last seen {mins}m ago", f"آخرین بازدید {mins} دقیقه پیش", f"Last seen {mins}m ago", False, dt_str
    elif diff_sec < 86400:
        hours = max(1, int(diff_sec / 3600))
        return f"Last seen {hours}h ago", f"آخرین بازدید {hours} ساعت پیش", f"Last seen {hours}h ago", False, dt_str
    elif diff_sec < 86400 * 2:
        return "Last seen yesterday", "آخرین بازدید دیروز", "Last seen yesterday", False, dt_str
    elif diff_sec < 86400 * 7:
        days = max(1, int(diff_sec / 86400))
        return f"Last seen {days} days ago", f"آخرین بازدید {days} روز پیش", f"Last seen {days} days ago", False, dt_str
    else:
        return "offline", "اخیراً آنلاین بوده", "Last seen recently", False, dt_str

def _format_student(
    user: User,
    lesson_id: UUID = None,
    latest_msg: Optional[Message] = None,
    session: Optional[UserSession] = None,
) -> StudentResponse:
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
    status_code, status_fa, status_en, is_online, last_active_str = _compute_session_status(session, user)

    if latest_msg:
        preview_text = latest_msg.text_content or ""
        dt_str = latest_msg.created_at.isoformat() if latest_msg.created_at else (user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat())
    else:
        if user.bio and not user.bio.startswith("دانشجوی درس سیستم عامل - وضعیت:"):
            preview_text = user.bio
        else:
            preview_text = status_fa
        dt_str = last_active_str or (user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat())

    return StudentResponse(
        id=user.user_id,
        lessonId=lesson_id,
        title=name,
        photo_url=user.profile_url,
        preview=preview_text,
        status=status_code,
        statusFa=status_fa,
        statusEn=status_en,
        is_online=is_online,
        last_active_at=last_active_str,
        date=dt_str,
        unreadCount=0,
        blocked=not (user.is_active if user.is_active is not None else True),
    )

def _resolve_course_id(course_id: str) -> UUID:
    if str(course_id).lower() in ("os", "operating-systems"):
        return UUID("c0000000-0000-4000-8000-000000000001")
    try:
        return UUID(course_id)
    except ValueError:
        return UUID("c0000000-0000-4000-8000-000000000001")

def _resolve_student_id(student_id: str) -> UUID:
    try:
        return UUID(student_id)
    except Exception:
        if str(student_id).isdigit():
            val = int(student_id)
            return UUID(f"20000000-0000-4000-8000-{val:012d}")
        import uuid as _u
        return _u.uuid5(UUID("20000000-0000-4000-8000-000000000000"), f"student:{student_id}")

@router.get("/courses/{course_id}/students", response_model=List[StudentResponse])
async def get_students_by_course(course_id: str, db: AsyncSession = Depends(get_db)):
    resolved_course_id = _resolve_course_id(course_id)
    stmt = (
        select(User)
        .join(LessonMember, LessonMember.user_id == User.user_id)
        .where(LessonMember.lesson_id == resolved_course_id)
        .order_by(User.first_name.asc())
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    # Fallback to all student users if none specifically enrolled
    if not users:
        stmt_all = select(User).where(User.user_type == "STUDENT").order_by(User.first_name.asc())
        result_all = await db.execute(stmt_all)
        users = result_all.scalars().all()

    latest_messages: Dict[UUID, Message] = {}
    latest_sessions: Dict[UUID, UserSession] = {}
    if users:
        user_ids = [u.user_id for u in users]
        stmt_msg = (
            select(Message)
            .where(Message.chat_id.in_(user_ids))
            .order_by(Message.chat_id, Message.created_at.desc())
            .distinct(Message.chat_id)
        )
        res_msg = await db.execute(stmt_msg)
        for msg in res_msg.scalars().all():
            latest_messages[msg.chat_id] = msg

        stmt_sess = (
            select(UserSession)
            .where(
                UserSession.user_id.in_(user_ids),
                UserSession.revoked_at.is_(None),
            )
            .order_by(UserSession.user_id, UserSession.last_active_at.desc())
            .distinct(UserSession.user_id)
        )
        res_sess = await db.execute(stmt_sess)
        for s in res_sess.scalars().all():
            latest_sessions[s.user_id] = s

    return [_format_student(u, resolved_course_id, latest_messages.get(u.user_id), latest_sessions.get(u.user_id)) for u in users]

@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student_by_id(student_id: str, db: AsyncSession = Depends(get_db)):
    resolved_student_id = _resolve_student_id(student_id)
    stmt = select(User).where(
        (User.user_id == resolved_student_id) | (User.username == student_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        stmt_name = select(User).where(User.first_name == student_id)
        res_name = await db.execute(stmt_name)
        user = res_name.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    stmt_member = select(LessonMember.lesson_id).where(LessonMember.user_id == user.user_id).limit(1)
    res_member = await db.execute(stmt_member)
    member_lesson_id = res_member.scalar_one_or_none() or UUID("c0000000-0000-4000-8000-000000000001")

    stmt_last_msg = (
        select(Message)
        .where(Message.chat_id == user.user_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    res_last_msg = await db.execute(stmt_last_msg)
    latest_msg = res_last_msg.scalar_one_or_none()

    stmt_sess = (
        select(UserSession)
        .where(
            UserSession.user_id == user.user_id,
            UserSession.revoked_at.is_(None),
        )
        .order_by(UserSession.last_active_at.desc())
        .limit(1)
    )
    res_sess = await db.execute(stmt_sess)
    user_session = res_sess.scalar_one_or_none()

    return _format_student(user, member_lesson_id, latest_msg, user_session)

@router.patch("/courses/{course_id}/students/{student_id}/block")
async def toggle_block_student(
    course_id: UUID,
    student_id: UUID,
    payload: BlockStudentRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.user_id == student_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    user.is_active = not payload.blocked
    await db.commit()

    return {"success": True, "studentId": student_id, "blocked": payload.blocked}

@router.delete("/courses/{course_id}/students/{student_id}")
async def remove_student_from_course(
    course_id: UUID,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    stmt = delete(LessonMember).where(
        LessonMember.lesson_id == course_id,
        LessonMember.user_id == student_id,
    )
    await db.execute(stmt)
    await db.commit()

    return {"success": True, "removedStudentId": student_id}
