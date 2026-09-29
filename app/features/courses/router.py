from typing import List, Optional, Dict
from uuid import UUID, uuid4
import os
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.security import decode_token
from app.features.users.models import User
from app.features.lessons.models import Lesson, LessonMember
from app.features.chat.models import Chat, Message, ChatJoinRequest
from .schemas import (
    CourseResponse,
    CourseDetailResponse,
    CourseUpdateRequest,
    CourseStatusUpdateRequest,
    CourseOverviewResponse,
    CategoryItem,
    RecentCourseItem,
    JoinCourseResponse,
)

router = APIRouter()

OS_COURSE_UUID = UUID("c0000000-0000-4000-8000-000000000001")

COURSE_METADATA = {
    OS_COURSE_UUID: {
        "degree": "کارشناسی",
        "units": 3,
        "course_code": "۲۱۱۰۰۱۲",
        "department": "مهندسی کامپیوتر",
        "term": "نیم‌سال دوم ۱۴۰۴-۱۴۰۵",
    },
}

def get_course_meta(lesson: Lesson) -> dict:
    meta = COURSE_METADATA.get(lesson.lesson_id, {})
    return {
        "degree": meta.get("degree", "کارشناسی"),
        "units": meta.get("units", 3),
        "course_code": meta.get("course_code", f"۲۱۱{abs(hash(str(lesson.lesson_id))) % 9000 + 1000}"),
        "department": meta.get("department", "مهندسی کامپیوتر"),
        "term": meta.get("term", "نیم‌سال دوم ۱۴۰۴-۱۴۰۵"),
    }

def resolve_course_uuid(course_id: str) -> UUID:
    if course_id.lower() in ("os", "operating-systems"):
        return OS_COURSE_UUID
    try:
        return UUID(course_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid course identifier",
        )

@router.get("", response_model=List[CourseResponse])
async def get_all_courses(
    active_only: bool = False,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Lesson).order_by(Lesson.created_at.asc())
    if active_only:
        stmt = stmt.where(Lesson.is_active == True)
    result = await db.execute(stmt)
    lessons = result.scalars().all()

    # Check if request comes from an authenticated student or teacher
    current_student_id: Optional[UUID] = None
    is_teacher = False
    if request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ")[1]
            try:
                payload = decode_token(raw_token)
                sub = payload.get("sub")
                if sub:
                    parsed_sub = UUID(sub)
                    stmt_user = select(User).where(User.user_id == parsed_sub)
                    res_user = await db.execute(stmt_user)
                    user = res_user.scalar_one_or_none()
                    if user:
                        if user.user_type == "TEACHER":
                            is_teacher = True
                        elif user.user_type == "STUDENT":
                            current_student_id = parsed_sub
            except Exception:
                pass

    # Query latest message for each lesson
    latest_messages: Dict[UUID, Message] = {}
    if lessons:
        lesson_ids = [l.lesson_id for l in lessons]
        if current_student_id:
            # Query student's personal message with the bot
            stmt_s = (
                select(Message)
                .where(Message.chat_id == current_student_id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            res_s = await db.execute(stmt_s)
            s_msg = res_s.scalar_one_or_none()
            if s_msg:
                for l in lessons:
                    latest_messages[l.lesson_id] = s_msg
        else:
            stmt_msg = (
                select(Message)
                .where(Message.chat_id.in_(lesson_ids))
                .order_by(Message.chat_id, Message.created_at.desc())
                .distinct(Message.chat_id)
            )
            res_msg = await db.execute(stmt_msg)
            for msg in res_msg.scalars().all():
                latest_messages[msg.chat_id] = msg

    # Calculate unread comments count for student
    unread_counts: Dict[UUID, int] = {}
    if lessons:
        check_chat_ids = [l.lesson_id for l in lessons]
        if current_student_id:
            check_chat_ids.append(current_student_id)

        stmt_unr = select(Message).where(
            Message.chat_id.in_(check_chat_ids),
            Message.metadata_json.isnot(None),
        )
        res_unr = await db.execute(stmt_unr)
        all_unr_msgs = res_unr.scalars().all()
        for u_msg in all_unr_msgs:
            if not u_msg.metadata_json or not isinstance(u_msg.metadata_json, dict):
                continue
            u_comments = u_msg.metadata_json.get("comments", [])
            for uc in u_comments:
                if not isinstance(uc, dict):
                    continue
                uc_read = uc.get("is_read", False)
                read_by = [str(x) for x in uc.get("read_by", [])]
                is_unread = not uc_read or (current_student_id and str(current_student_id) not in read_by)
                if is_unread:
                    target_l_id = u_msg.chat_id if u_msg.chat_id in [l.lesson_id for l in lessons] else OS_COURSE_UUID
                    unread_counts[target_l_id] = unread_counts.get(target_l_id, 0) + 1

    # Query enrolled courses and pending join requests for student
    enrolled_lesson_ids = set()
    pending_lesson_ids = set()
    if current_student_id:
        stmt_enl = select(LessonMember.lesson_id).where(LessonMember.user_id == current_student_id)
        res_enl = await db.execute(stmt_enl)
        enrolled_lesson_ids = set(res_enl.scalars().all())

        stmt_pnd = select(ChatJoinRequest.chat_id).where(
            ChatJoinRequest.user_id == current_student_id,
            ChatJoinRequest.status == "PENDING"
        )
        res_pnd = await db.execute(stmt_pnd)
        pending_lesson_ids = set(res_pnd.scalars().all())

    # Resolve real teacher names from users table
    teachers_map: Dict[UUID, str] = {}
    teacher_ids = [l.teacher_id for l in lessons if l.teacher_id]
    if teacher_ids:
        stmt_t = select(User).where(User.user_id.in_(teacher_ids))
        res_t = await db.execute(stmt_t)
        for t_user in res_t.scalars().all():
            full = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.username
            teachers_map[t_user.user_id] = full

    courses = []
    for l in lessons:
        msg = latest_messages.get(l.lesson_id)
        if msg:
            preview_text = msg.text_content or ""
            dt_str = msg.created_at.isoformat() if msg.created_at else datetime.now(timezone.utc).isoformat()
        else:
            preview_text = (
                l.description[:60] + "..."
                if l.description and len(l.description) > 60
                else (l.description or "")
            )
            dt_str = l.created_at.isoformat() if l.created_at else datetime.now(timezone.utc).isoformat()

        t_name = teachers_map.get(l.teacher_id)
        is_enrolled = (l.lesson_id in enrolled_lesson_ids)
        has_pending = (l.lesson_id in pending_lesson_ids)

        # Private courses are hidden unless the user is a teacher or already enrolled
        if not is_teacher and not l.is_public and not is_enrolled:
            continue

        meta = get_course_meta(l)
        courses.append(
            CourseResponse(
                id=l.lesson_id,
                title=l.title,
                titleFa=l.title,
                titleEn=l.title,
                preview=preview_text,
                previewEn="This course includes educational materials and related resources.",
                description=l.description or "",
                descriptionEn="This course includes educational materials and related resources.",
                accessLevel="public" if l.is_public else "private",
                photo_url=l.avatar_url,
                date=dt_str,
                unreadCount=unread_counts.get(l.lesson_id, 0),
                teacher_name=t_name,
                instructor_name=t_name,
                isActive=l.is_active if l.is_active is not None else True,
                is_active=l.is_active if l.is_active is not None else True,
                is_enrolled=is_enrolled,
                has_pending_request=has_pending,
                degree=meta["degree"],
                units=meta["units"],
                course_code=meta["course_code"],
                department=meta["department"],
                term=meta["term"],
            )
        )
    return courses

@router.get("/overview", response_model=CourseOverviewResponse)
async def get_courses_overview(db: AsyncSession = Depends(get_db)):
    stmt = select(Lesson).where(Lesson.is_active == True).order_by(Lesson.created_at.asc()).limit(5)
    result = await db.execute(stmt)
    lessons = result.scalars().all()

    categories = [
        CategoryItem(id="operating-systems", name="سیستم عامل"),
        CategoryItem(id="artificial-intelligence", name="هوش مصنوعی"),
        CategoryItem(id="data-security", name="امنیت داده‌ها"),
        CategoryItem(id="software-engineering", name="مهندسی نرم‌افزار"),
        CategoryItem(id="networks", name="شبکه‌های کامپیوتری"),
    ]

    recent_courses = [
        RecentCourseItem(
            id=l.lesson_id,
            name=l.title,
            visibility="Private" if not l.is_public else "Public",
        )
        for l in lessons
    ]

    return CourseOverviewResponse(categories=categories, recentCourses=recent_courses)

@router.get("/{course_id}", response_model=CourseResponse)
async def get_course_by_id(
    course_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if request comes from an authenticated student
    current_student_id: Optional[UUID] = None
    if request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ")[1]
            try:
                payload = decode_token(raw_token)
                sub = payload.get("sub")
                if sub:
                    parsed_sub = UUID(sub)
                    stmt_user = select(User).where(User.user_id == parsed_sub)
                    res_user = await db.execute(stmt_user)
                    user = res_user.scalar_one_or_none()
                    if user and user.user_type == "STUDENT":
                        current_student_id = parsed_sub
            except Exception:
                pass

    if current_student_id:
        stmt_msg = (
            select(Message)
            .where(Message.chat_id == current_student_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    else:
        stmt_msg = (
            select(Message)
            .where(Message.chat_id == resolved_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    res_msg = await db.execute(stmt_msg)
    msg = res_msg.scalar_one_or_none()

    if msg:
        preview_text = msg.text_content or ""
        dt_str = msg.created_at.isoformat() if msg.created_at else datetime.now(timezone.utc).isoformat()
    else:
        preview_text = (
            lesson.description[:60] + "..."
            if lesson.description and len(lesson.description) > 60
            else (lesson.description or "")
        )
        dt_str = lesson.created_at.isoformat() if lesson.created_at else datetime.now(timezone.utc).isoformat()

    teacher_name = None
    if lesson.teacher_id:
        stmt_t = select(User).where(User.user_id == lesson.teacher_id)
        res_t = await db.execute(stmt_t)
        t_user = res_t.scalar_one_or_none()
        if t_user:
            teacher_name = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.username

    is_enrolled = False
    has_pending = False
    if current_student_id:
        stmt_mem = select(LessonMember).where(
            LessonMember.lesson_id == resolved_id,
            LessonMember.user_id == current_student_id
        )
        res_mem = await db.execute(stmt_mem)
        is_enrolled = res_mem.scalar_one_or_none() is not None

        stmt_pnd = select(ChatJoinRequest).where(
            ChatJoinRequest.chat_id == resolved_id,
            ChatJoinRequest.user_id == current_student_id,
            ChatJoinRequest.status == "PENDING"
        )
        res_pnd = await db.execute(stmt_pnd)
        has_pending = res_pnd.scalar_one_or_none() is not None

    return CourseResponse(
        id=lesson.lesson_id,
        title=lesson.title,
        titleFa=lesson.title,
        titleEn=lesson.title,
        preview=preview_text,
        previewEn="This course includes educational materials and related resources.",
        description=lesson.description or "",
        descriptionEn="This course includes educational materials and related resources.",
        accessLevel="public" if lesson.is_public else "private",
        photo_url=lesson.avatar_url,
        date=dt_str,
        unreadCount=0,
        teacher_name=teacher_name,
        instructor_name=teacher_name,
        isActive=lesson.is_active if lesson.is_active is not None else True,
        is_active=lesson.is_active if lesson.is_active is not None else True,
        is_enrolled=is_enrolled,
        has_pending_request=has_pending,
    )

@router.post("/{course_id}/join", response_model=JoinCourseResponse)
async def join_or_request_course(
    course_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    current_user_id: Optional[UUID] = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ")[1]
        try:
            payload = decode_token(raw_token)
            sub = payload.get("sub")
            if sub:
                current_user_id = UUID(sub)
        except Exception:
            pass

    if not current_user_id:
        stmt_st = select(User).where(User.user_type == "STUDENT").limit(1)
        res_st = await db.execute(stmt_st)
        st_user = res_st.scalar_one_or_none()
        if st_user:
            current_user_id = st_user.user_id

    if not current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to join course",
        )

    # Check if already enrolled
    stmt_mem = select(LessonMember).where(
        LessonMember.lesson_id == resolved_id,
        LessonMember.user_id == current_user_id
    )
    res_mem = await db.execute(stmt_mem)
    existing_mem = res_mem.scalar_one_or_none()
    if existing_mem:
        return JoinCourseResponse(
            success=True,
            status="enrolled",
            message="شما در حال حاضر عضو این درس هستید.",
            course_id=resolved_id,
        )

    # Ensure a corresponding Chat row exists (chat_join_requests references chats.chat_id)
    stmt_c = select(Chat).where(Chat.chat_id == resolved_id)
    res_c = await db.execute(stmt_c)
    chat = res_c.scalar_one_or_none()
    if not chat:
        chat = Chat(
            chat_id=resolved_id,
            chat_type="COURSE",
            title=lesson.title,
            is_public=lesson.is_public,
        )
        db.add(chat)
        await db.flush()

    # Create or verify pending join request (both public and private courses require teacher approval)
    stmt_req = select(ChatJoinRequest).where(
        ChatJoinRequest.chat_id == resolved_id,
        ChatJoinRequest.user_id == current_user_id,
        ChatJoinRequest.status == "PENDING"
    )
    res_req = await db.execute(stmt_req)
    existing_req = res_req.scalar_one_or_none()
    if existing_req:
        return JoinCourseResponse(
            success=True,
            status="pending",
            message="درخواست عضویت شما قبلاً ارسال شده و در انتظار تأیید استاد است.",
            course_id=resolved_id,
        )

    join_req = ChatJoinRequest(
        chat_id=resolved_id,
        user_id=current_user_id,
        status="PENDING",
    )
    db.add(join_req)
    await db.commit()

    return JoinCourseResponse(
        success=True,
        status="pending",
        message="درخواست عضویت با موفقیت برای استاد ارسال شد.",
        course_id=resolved_id,
    )

@router.get("/{course_id}/details", response_model=CourseDetailResponse)
async def get_course_details(course_id: str, db: AsyncSession = Depends(get_db)):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    teacher_name = None
    if lesson.teacher_id:
        stmt_t = select(User).where(User.user_id == lesson.teacher_id)
        res_t = await db.execute(stmt_t)
        t_user = res_t.scalar_one_or_none()
        if t_user:
            teacher_name = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.username

    meta = get_course_meta(lesson)
    return CourseDetailResponse(
        courseId=lesson.lesson_id,
        name=lesson.title,
        nameFa=lesson.title,
        nameEn=lesson.title,
        teacher_name=teacher_name,
        instructor_name=teacher_name,
        startDate=lesson.start_date.strftime("%Y-%m-%d") if lesson.start_date else "2026-04-10",
        endDate=lesson.end_date.strftime("%Y-%m-%d") if lesson.end_date else "2026-08-20",
        description=lesson.description or "",
        accessLevel="public" if lesson.is_public else "private",
        photo_url=lesson.avatar_url,
        isActive=lesson.is_active if lesson.is_active is not None else True,
        is_active=lesson.is_active if lesson.is_active is not None else True,
        degree=meta["degree"],
        units=meta["units"],
        course_code=meta["course_code"],
        department=meta["department"],
        term=meta["term"],
    )

@router.put("/{course_id}/details")
async def update_course_details(
    course_id: str,
    payload: CourseUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    if payload.name is not None:
        lesson.title = payload.name
    if payload.description is not None:
        lesson.description = payload.description
    if payload.accessLevel is not None:
        lesson.is_public = (payload.accessLevel.lower() == "public")
    if payload.isActive is not None:
        lesson.is_active = payload.isActive
    elif payload.is_active is not None:
        lesson.is_active = payload.is_active
    if payload.startDate is not None:
        try:
            lesson.start_date = datetime.fromisoformat(payload.startDate)
        except Exception:
            try:
                lesson.start_date = datetime.strptime(payload.startDate, "%Y-%m-%d")
            except Exception:
                pass
    if payload.endDate is not None:
        try:
            lesson.end_date = datetime.fromisoformat(payload.endDate)
        except Exception:
            try:
                lesson.end_date = datetime.strptime(payload.endDate, "%Y-%m-%d")
            except Exception:
                pass

    await db.commit()
    await db.refresh(lesson)

    return {
        "success": True,
        "courseId": resolved_id,
        "isActive": lesson.is_active,
        "is_active": lesson.is_active,
        "data": payload.model_dump(exclude_none=True),
    }

@router.patch("/{course_id}/status")
async def update_course_status(
    course_id: str,
    payload: CourseStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    new_status = payload.isActive if payload.isActive is not None else payload.is_active
    if new_status is not None:
        lesson.is_active = new_status
        await db.commit()
        await db.refresh(lesson)

    return {
        "success": True,
        "courseId": resolved_id,
        "isActive": lesson.is_active,
        "is_active": lesson.is_active,
    }

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/{course_id}/photo")
async def upload_course_photo(
    course_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        if file.content_type in ("image/png",):
            ext = ".png"
        elif file.content_type in ("image/webp",):
            ext = ".webp"
        elif file.content_type in ("image/gif",):
            ext = ".gif"
        elif file.content_type in ("image/jpeg", "image/jpg"):
            ext = ".jpg"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="فرمت فایل مجاز نیست. لطفاً عکس با فرمت JPG، PNG یا WebP ارسال کنید.",
            )

    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حجم عکس نباید بیشتر از ۱۰ مگابایت باشد.",
        )

    upload_dir = Path("uploads/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"course_{resolved_id}_{uuid4().hex[:12]}{ext}"
    file_path = upload_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)

    photo_url = f"/bot/v1/uploads/avatars/{filename}"
    lesson.avatar_url = photo_url

    # Also update or create Chat entry
    stmt_chat = select(Chat).where(Chat.chat_id == resolved_id)
    res_chat = await db.execute(stmt_chat)
    chat = res_chat.scalar_one_or_none()
    if chat:
        chat.avatar_url = photo_url
    else:
        chat = Chat(
            chat_id=resolved_id,
            chat_type="COURSE",
            title=lesson.title,
            avatar_url=photo_url,
            is_public=False,
        )
        db.add(chat)

    await db.commit()
    await db.refresh(lesson)

    return {
        "success": True,
        "courseId": resolved_id,
        "photo_url": photo_url,
    }

@router.delete("/{course_id}/photo")
async def delete_course_photo(
    course_id: str,
    db: AsyncSession = Depends(get_db),
):
    resolved_id = resolve_course_uuid(course_id)
    stmt = select(Lesson).where(Lesson.lesson_id == resolved_id)
    result = await db.execute(stmt)
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    old_url = lesson.avatar_url
    lesson.avatar_url = None

    stmt_chat = select(Chat).where(Chat.chat_id == resolved_id)
    res_chat = await db.execute(stmt_chat)
    chat = res_chat.scalar_one_or_none()
    if chat:
        chat.avatar_url = None

    if old_url and "/uploads/avatars/" in old_url:
        old_filename = old_url.split("/uploads/avatars/")[-1]
        old_path = Path("uploads/avatars") / old_filename
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

    await db.commit()
    await db.refresh(lesson)

    return {
        "success": True,
        "courseId": resolved_id,
        "photo_url": None,
    }
