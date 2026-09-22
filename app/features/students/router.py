from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.features.users.models import User
from app.features.lessons.models import LessonMember
from app.features.chat.models import Message
from .schemas import StudentResponse, BlockStudentRequest

router = APIRouter()

def _format_student(user: User, lesson_id: UUID = None, latest_msg: Optional[Message] = None) -> StudentResponse:
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
    if latest_msg:
        preview_text = latest_msg.text_content or ""
        dt_str = latest_msg.created_at.isoformat() if latest_msg.created_at else (user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat())
    else:
        preview_text = user.bio or ""
        dt_str = user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat()

    return StudentResponse(
        id=user.user_id,
        lessonId=lesson_id,
        title=name,
        photo_url=user.profile_url,
        preview=preview_text,
        status="online",
        statusFa="آنلاین",
        statusEn="Online",
        date=dt_str,
        unreadCount=0,
        blocked=not (user.is_active if user.is_active is not None else True),
    )

@router.get("/courses/{course_id}/students", response_model=List[StudentResponse])
async def get_students_by_course(course_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .join(LessonMember, LessonMember.user_id == User.user_id)
        .where(LessonMember.lesson_id == course_id)
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

    return [_format_student(u, course_id, latest_messages.get(u.user_id)) for u in users]

@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student_by_id(student_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.user_id == student_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    return _format_student(user)

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
