from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.security import decode_token
from app.features.users.models import User
from app.features.lessons.models import Lesson, LessonMember
from app.features.chat.models import ChatJoinRequest
from .schemas import TeacherJoinRequestResponse, StudentNotificationResponse

router = APIRouter()

def get_current_user_id(request: Request) -> Optional[UUID]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ")[1]
        try:
            payload = decode_token(raw_token)
            sub = payload.get("sub")
            if sub:
                return UUID(sub)
        except Exception:
            pass
    return None

@router.get("/join-requests", response_model=List[TeacherJoinRequestResponse])
async def get_teacher_join_requests(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    teacher_id = get_current_user_id(request)
    if not teacher_id:
        return []

    # Check caller role: students must NEVER see join requests
    stmt_t = select(User).where(User.user_id == teacher_id)
    res_t = await db.execute(stmt_t)
    caller = res_t.scalar_one_or_none()
    if not caller or caller.user_type != "TEACHER":
        return []

    # Query pending join requests for this teacher's lessons
    stmt = (
        select(ChatJoinRequest, User, Lesson)
        .join(User, ChatJoinRequest.user_id == User.user_id)
        .join(Lesson, ChatJoinRequest.chat_id == Lesson.lesson_id)
        .where(
            ChatJoinRequest.status == "PENDING",
            Lesson.teacher_id == teacher_id,
        )
        .order_by(ChatJoinRequest.requested_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    requests_list = []
    for req, student, lesson in rows:
        name = f"{student.first_name or ''} {student.last_name or ''}".strip() or student.username
        req_dt = req.requested_at.isoformat() if req.requested_at else datetime.now(timezone.utc).isoformat()
        requests_list.append(
            TeacherJoinRequestResponse(
                id=req.join_request_id,
                student_id=student.user_id,
                student_name=name,
                student_username=student.username,
                student_avatar=student.profile_url,
                course_id=lesson.lesson_id,
                course_title=lesson.title,
                requested_at=req_dt,
                status=req.status or "PENDING",
            )
        )

    return requests_list

@router.post("/join-requests/{request_id}/accept")
async def accept_join_request(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    teacher_id = get_current_user_id(request)

    stmt = select(ChatJoinRequest).where(ChatJoinRequest.join_request_id == request_id)
    res = await db.execute(stmt)
    join_req = res.scalar_one_or_none()

    if not join_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Join request not found",
        )

    join_req.status = "APPROVED"
    join_req.reviewed_at = datetime.now(timezone.utc)
    if teacher_id:
        join_req.reviewed_by_user_id = teacher_id

    # Check if student is already a lesson member
    stmt_mem = select(LessonMember).where(
        LessonMember.lesson_id == join_req.chat_id,
        LessonMember.user_id == join_req.user_id,
    )
    res_mem = await db.execute(stmt_mem)
    existing_mem = res_mem.scalar_one_or_none()

    if not existing_mem:
        new_member = LessonMember(
            lesson_id=join_req.chat_id,
            user_id=join_req.user_id,
            role="STUDENT",
        )
        db.add(new_member)

    await db.commit()

    return {
        "success": True,
        "requestId": str(request_id),
        "status": "accepted",
    }

@router.post("/join-requests/{request_id}/reject")
async def reject_join_request(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    teacher_id = get_current_user_id(request)

    stmt = select(ChatJoinRequest).where(ChatJoinRequest.join_request_id == request_id)
    res = await db.execute(stmt)
    join_req = res.scalar_one_or_none()

    if not join_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Join request not found",
        )

    join_req.status = "REJECTED"
    join_req.reviewed_at = datetime.now(timezone.utc)
    if teacher_id:
        join_req.reviewed_by_user_id = teacher_id

    await db.commit()

    return {
        "success": True,
        "requestId": str(request_id),
        "status": "rejected",
    }

@router.get("/student-notifications", response_model=List[StudentNotificationResponse])
async def get_student_notifications(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return []

    stmt_u = select(User).where(User.user_id == user_id)
    res_u = await db.execute(stmt_u)
    user = res_u.scalar_one_or_none()
    if not user:
        return []

    # Get approved join requests for this student
    stmt = (
        select(ChatJoinRequest, Lesson)
        .join(Lesson, ChatJoinRequest.chat_id == Lesson.lesson_id)
        .where(
            ChatJoinRequest.user_id == user_id,
            ChatJoinRequest.status == "APPROVED",
        )
        .order_by(ChatJoinRequest.reviewed_at.desc(), ChatJoinRequest.requested_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    notifications = []
    for req, lesson in rows:
        dt = req.reviewed_at or req.requested_at
        dt_str = dt.isoformat() if dt else datetime.now(timezone.utc).isoformat()
        notifications.append(
            StudentNotificationResponse(
                id=req.join_request_id,
                title="تأیید درخواست عضویت",
                message=f"درخواست عضویت شما در درس «{lesson.title}» تأیید شد.",
                course_id=lesson.lesson_id,
                course_title=lesson.title,
                course_avatar=lesson.avatar_url,
                date=dt_str,
                status="APPROVED",
                type="membership_approved",
            )
        )
    return notifications

@router.get("/messages")
async def get_teacher_system_messages():
    return []

@router.get("/unread-count")
async def get_unread_notifications_count(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = get_current_user_id(request)
    if not user_id:
        return {"count": 0}

    stmt_u = select(User).where(User.user_id == user_id)
    res_u = await db.execute(stmt_u)
    user = res_u.scalar_one_or_none()
    if not user:
        return {"count": 0}

    if user.user_type == "TEACHER":
        stmt = (
            select(func.count(ChatJoinRequest.join_request_id))
            .join(Lesson, ChatJoinRequest.chat_id == Lesson.lesson_id)
            .where(ChatJoinRequest.status == "PENDING", Lesson.teacher_id == user_id)
        )
        res = await db.execute(stmt)
        return {"count": res.scalar() or 0}

    if user.user_type == "STUDENT":
        stmt = (
            select(func.count(ChatJoinRequest.join_request_id))
            .where(
                ChatJoinRequest.user_id == user_id,
                ChatJoinRequest.status == "APPROVED",
            )
        )
        res = await db.execute(stmt)
        return {"count": res.scalar() or 0}

    return {"count": 0}
