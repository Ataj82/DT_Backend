# app/features/admin/router.py
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.features.users.models import User
from app.features.lessons.models import Lesson, LessonMember
from app.features.courses.router import COURSE_METADATA

router = APIRouter()


# ========================= Schemas =========================

class AdminAssignTeacherRequest(BaseModel):
    teacher_id: UUID


class AdminAddMemberRequest(BaseModel):
    user_id: UUID
    role: str = "STUDENT"


class AdminCourseMemberItem(BaseModel):
    lesson_member_id: UUID
    user_id: UUID
    username: str
    full_name: str
    role: str
    joined_at: Optional[datetime] = None


class AdminAvailableStudentItem(BaseModel):
    user_id: UUID
    username: str
    full_name: str


class AdminOverviewResponse(BaseModel):
    total_courses: int
    active_courses: int
    total_users: int
    total_students: int
    total_teachers: int
    total_admins: int
    total_enrollments: int


class AdminCourseItem(BaseModel):
    course_id: UUID
    title: str
    description: Optional[str] = None
    subject: Optional[str] = None
    units: int = 3
    teacher_id: Optional[UUID] = None
    teacher_name: Optional[str] = None
    teacher_username: Optional[str] = None
    is_active: bool = True
    is_public: bool = False
    students_count: int = 0
    created_at: Optional[datetime] = None


class AdminCourseCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(default="", max_length=2000)
    subject: Optional[str] = Field(default="مهندسی کامپیوتر", max_length=128)
    teacher_id: UUID
    units: int = Field(default=3, ge=1, le=6)
    is_public: bool = False
    is_active: bool = True


class AdminUserItem(BaseModel):
    user_id: UUID
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    user_type: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class AdminTeacherOption(BaseModel):
    teacher_id: UUID
    username: str
    name: str
    email: Optional[str] = None


# ========================= Endpoints =========================

@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(db: AsyncSession = Depends(get_db)):
    """Returns aggregated high-level statistics for the admin dashboard."""
    # Count courses
    res_courses = await db.execute(select(func.count(Lesson.lesson_id)))
    total_courses = res_courses.scalar() or 0

    res_active_courses = await db.execute(
        select(func.count(Lesson.lesson_id)).where(Lesson.is_active == True)
    )
    active_courses = res_active_courses.scalar() or 0

    # Count users by type
    res_users = await db.execute(select(func.count(User.user_id)))
    total_users = res_users.scalar() or 0

    res_students = await db.execute(
        select(func.count(User.user_id)).where(User.user_type == "STUDENT")
    )
    total_students = res_students.scalar() or 0

    res_teachers = await db.execute(
        select(func.count(User.user_id)).where(User.user_type == "TEACHER")
    )
    total_teachers = res_teachers.scalar() or 0

    res_admins = await db.execute(
        select(func.count(User.user_id)).where(User.user_type == "ADMIN")
    )
    total_admins = res_admins.scalar() or 0

    # Count student enrollments
    res_enrollments = await db.execute(
        select(func.count(LessonMember.lesson_member_id)).where(LessonMember.role == "STUDENT")
    )
    total_enrollments = res_enrollments.scalar() or 0

    return AdminOverviewResponse(
        total_courses=total_courses,
        active_courses=active_courses,
        total_users=total_users,
        total_students=total_students,
        total_teachers=total_teachers,
        total_admins=total_admins,
        total_enrollments=total_enrollments,
    )


@router.get("/courses", response_model=List[AdminCourseItem])
async def get_admin_courses(db: AsyncSession = Depends(get_db)):
    """Returns all courses with instructor information and enrolled student counts."""
    # Query all lessons
    stmt_lessons = select(Lesson).order_by(Lesson.created_at.desc())
    res_lessons = await db.execute(stmt_lessons)
    lessons = res_lessons.scalars().all()

    if not lessons:
        return []

    # Query teachers
    teacher_ids = [l.teacher_id for l in lessons if l.teacher_id]
    teachers_map = {}
    if teacher_ids:
        stmt_t = select(User).where(User.user_id.in_(teacher_ids))
        res_t = await db.execute(stmt_t)
        for t in res_t.scalars().all():
            teachers_map[t.user_id] = t

    # Query enrolled student counts
    stmt_counts = (
        select(LessonMember.lesson_id, func.count(LessonMember.lesson_member_id))
        .where(LessonMember.role == "STUDENT")
        .group_by(LessonMember.lesson_id)
    )
    res_counts = await db.execute(stmt_counts)
    counts_map = {row[0]: row[1] for row in res_counts.all()}

    items: List[AdminCourseItem] = []
    for l in lessons:
        teacher = teachers_map.get(l.teacher_id)
        if teacher:
            t_full = f"{teacher.first_name or ''} {teacher.last_name or ''}".strip() or teacher.username
            t_user = teacher.username
        else:
            t_full = "تعیین‌نشده"
            t_user = "unknown"

        meta = COURSE_METADATA.get(l.lesson_id, {})
        course_units = meta.get("units", 3)

        items.append(
            AdminCourseItem(
                course_id=l.lesson_id,
                title=l.title,
                description=l.description or "",
                subject=l.subject or meta.get("department", "مهندسی کامپیوتر"),
                units=course_units,
                teacher_id=l.teacher_id,
                teacher_name=t_full,
                teacher_username=t_user,
                is_active=bool(l.is_active),
                is_public=bool(l.is_public),
                students_count=counts_map.get(l.lesson_id, 0),
                created_at=l.created_at,
            )
        )

    return items


@router.post("/courses", response_model=AdminCourseItem, status_code=status.HTTP_201_CREATED)
async def create_admin_course(payload: AdminCourseCreate, db: AsyncSession = Depends(get_db)):
    """Creates a new course, assigns the selected instructor, and creates the course bot."""
    # 1. Verify selected teacher exists
    stmt_t = select(User).where(User.user_id == payload.teacher_id)
    res_t = await db.execute(stmt_t)
    teacher = res_t.scalar_one_or_none()
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specified instructor not found",
        )

    # 2. Provision dedicated course bot user
    bot_username = f"bot_{uuid4().hex[:8]}"
    bot_user = User(
        user_id=uuid4(),
        username=bot_username,
        hashed_password="",
        first_name="Lesson Bot -",
        last_name=payload.title,
        user_type="bot",
        is_active=True,
    )
    db.add(bot_user)
    await db.flush()

    # 3. Create Lesson record
    new_lesson_id = uuid4()
    lesson = Lesson(
        lesson_id=new_lesson_id,
        title=payload.title,
        description=payload.description,
        subject=payload.subject,
        teacher_id=payload.teacher_id,
        bot_user_id=bot_user.user_id,
        is_active=payload.is_active,
        is_public=payload.is_public,
    )
    db.add(lesson)
    await db.flush()

    # 4. Add instructor to lesson_members
    member = LessonMember(
        lesson_member_id=uuid4(),
        lesson_id=new_lesson_id,
        user_id=payload.teacher_id,
        role="TEACHER",
    )
    db.add(member)
    await db.commit()
    await db.refresh(lesson)

    # 5. Register in runtime COURSE_METADATA cache
    COURSE_METADATA[new_lesson_id] = {
        "degree": "کارشناسی",
        "units": payload.units,
        "course_code": f"۲۱۱{abs(hash(str(new_lesson_id))) % 9000 + 1000}",
        "department": payload.subject or "مهندسی کامپیوتر",
        "term": "نیم‌سال دوم ۱۴۰۴-۱۴۰۵",
    }

    t_full = f"{teacher.first_name or ''} {teacher.last_name or ''}".strip() or teacher.username

    return AdminCourseItem(
        course_id=lesson.lesson_id,
        title=lesson.title,
        description=lesson.description or "",
        subject=lesson.subject or payload.subject,
        units=payload.units,
        teacher_id=lesson.teacher_id,
        teacher_name=t_full,
        teacher_username=teacher.username,
        is_active=lesson.is_active,
        is_public=lesson.is_public,
        students_count=0,
        created_at=lesson.created_at,
    )


@router.get("/users", response_model=List[AdminUserItem])
async def get_admin_users(
    role: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Returns user list with optional role filter and search term."""
    stmt = select(User).where(User.user_type != "bot").order_by(User.created_at.desc()).limit(limit)

    if role and role.upper() != "ALL":
        stmt = stmt.where(User.user_type == role.upper())

    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(search_pattern),
                User.first_name.ilike(search_pattern),
                User.last_name.ilike(search_pattern),
            )
        )

    res = await db.execute(stmt)
    users = res.scalars().all()

    items: List[AdminUserItem] = []
    for u in users:
        full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username
        items.append(
            AdminUserItem(
                user_id=u.user_id,
                username=u.username,
                first_name=u.first_name,
                last_name=u.last_name,
                full_name=full_name,
                user_type=u.user_type,
                is_active=bool(u.is_active),
                created_at=u.created_at,
                last_seen_at=u.last_seen_at,
            )
        )

    return items


@router.get("/teachers", response_model=List[AdminTeacherOption])
async def get_admin_teachers(db: AsyncSession = Depends(get_db)):
    """Returns active instructors for the course creation dropdown selector."""
    stmt = select(User).where(User.user_type == "TEACHER", User.is_active == True).order_by(User.last_name.asc())
    res = await db.execute(stmt)
    teachers = res.scalars().all()

    return [
        AdminTeacherOption(
            teacher_id=t.user_id,
            username=t.username,
            name=f"{t.first_name or ''} {t.last_name or ''}".strip() or t.username,
            email=f"{t.username}@iau.ac.ir",
        )
        for t in teachers
    ]


# ========================= Course Membership & Teacher Management =========================

@router.get("/courses/{course_id}/members", response_model=List[AdminCourseMemberItem])
async def get_course_members(course_id: UUID, db: AsyncSession = Depends(get_db)):
    """Returns all members (students & teacher) enrolled in the specified course."""
    stmt = (
        select(LessonMember, User)
        .join(User, LessonMember.user_id == User.user_id)
        .where(LessonMember.lesson_id == course_id)
        .order_by(LessonMember.role.desc(), User.last_name.asc())
    )
    res = await db.execute(stmt)
    members = res.all()

    items = []
    for member, user in members:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        items.append(
            AdminCourseMemberItem(
                lesson_member_id=member.lesson_member_id,
                user_id=user.user_id,
                username=user.username,
                full_name=full_name,
                role=member.role,
                joined_at=member.joined_at,
            )
        )
    return items


@router.get("/courses/{course_id}/available-students", response_model=List[AdminAvailableStudentItem])
async def get_available_students_for_course(course_id: UUID, db: AsyncSession = Depends(get_db)):
    """Returns students who are not yet enrolled in the course."""
    subq = select(LessonMember.user_id).where(LessonMember.lesson_id == course_id)
    stmt = (
        select(User)
        .where(User.user_type == "STUDENT", User.is_active == True, User.user_id.not_in(subq))
        .order_by(User.last_name.asc())
    )
    res = await db.execute(stmt)
    users = res.scalars().all()

    return [
        AdminAvailableStudentItem(
            user_id=u.user_id,
            username=u.username,
            full_name=f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username,
        )
        for u in users
    ]


@router.post("/courses/{course_id}/teacher", response_model=AdminCourseItem)
async def assign_course_teacher(
    course_id: UUID,
    payload: AdminAssignTeacherRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reassigns or updates the instructor for a course."""
    stmt_l = select(Lesson).where(Lesson.lesson_id == course_id)
    res_l = await db.execute(stmt_l)
    lesson = res_l.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    stmt_t = select(User).where(User.user_id == payload.teacher_id, User.user_type == "TEACHER")
    res_t = await db.execute(stmt_t)
    new_teacher = res_t.scalar_one_or_none()
    if not new_teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    old_teacher_id = lesson.teacher_id
    lesson.teacher_id = payload.teacher_id

    # 1. Remove old teacher membership if different
    if old_teacher_id and old_teacher_id != payload.teacher_id:
        await db.execute(
            delete(LessonMember).where(
                LessonMember.lesson_id == course_id,
                LessonMember.user_id == old_teacher_id,
                LessonMember.role == "TEACHER",
            )
        )

    # 2. Check if new teacher is already a member
    stmt_m = select(LessonMember).where(
        LessonMember.lesson_id == course_id,
        LessonMember.user_id == payload.teacher_id,
    )
    res_m = await db.execute(stmt_m)
    existing_member = res_m.scalar_one_or_none()
    if existing_member:
        existing_member.role = "TEACHER"
    else:
        new_m = LessonMember(
            lesson_member_id=uuid4(),
            lesson_id=course_id,
            user_id=payload.teacher_id,
            role="TEACHER",
        )
        db.add(new_m)

    await db.commit()
    await db.refresh(lesson)

    # Calculate student count
    res_c = await db.execute(
        select(func.count(LessonMember.lesson_member_id)).where(
            LessonMember.lesson_id == course_id,
            LessonMember.role == "STUDENT",
        )
    )
    students_count = res_c.scalar() or 0

    meta = COURSE_METADATA.get(course_id, {})
    t_full = f"{new_teacher.first_name or ''} {new_teacher.last_name or ''}".strip() or new_teacher.username

    return AdminCourseItem(
        course_id=lesson.lesson_id,
        title=lesson.title,
        description=lesson.description or "",
        subject=lesson.subject or meta.get("department", "مهندسی کامپیوتر"),
        units=meta.get("units", 3),
        teacher_id=lesson.teacher_id,
        teacher_name=t_full,
        teacher_username=new_teacher.username,
        is_active=lesson.is_active,
        is_public=lesson.is_public,
        students_count=students_count,
        created_at=lesson.created_at,
    )


@router.post("/courses/{course_id}/members", response_model=AdminCourseMemberItem, status_code=status.HTTP_201_CREATED)
async def add_course_member(
    course_id: UUID,
    payload: AdminAddMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enrolls a student or user into the course."""
    stmt_l = select(Lesson).where(Lesson.lesson_id == course_id)
    res_l = await db.execute(stmt_l)
    lesson = res_l.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    stmt_u = select(User).where(User.user_id == payload.user_id)
    res_u = await db.execute(stmt_u)
    user = res_u.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check existing membership
    stmt_m = select(LessonMember).where(
        LessonMember.lesson_id == course_id,
        LessonMember.user_id == payload.user_id,
    )
    res_m = await db.execute(stmt_m)
    existing_m = res_m.scalar_one_or_none()
    if existing_m:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        return AdminCourseMemberItem(
            lesson_member_id=existing_m.lesson_member_id,
            user_id=user.user_id,
            username=user.username,
            full_name=full_name,
            role=existing_m.role,
            joined_at=existing_m.joined_at,
        )

    new_member = LessonMember(
        lesson_member_id=uuid4(),
        lesson_id=course_id,
        user_id=payload.user_id,
        role=payload.role.upper(),
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)

    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
    return AdminCourseMemberItem(
        lesson_member_id=new_member.lesson_member_id,
        user_id=user.user_id,
        username=user.username,
        full_name=full_name,
        role=new_member.role,
        joined_at=new_member.joined_at,
    )


@router.delete("/courses/{course_id}/members/{user_id}")
async def remove_course_member(
    course_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Removes a user/student from the course roster."""
    stmt_l = select(Lesson).where(Lesson.lesson_id == course_id)
    res_l = await db.execute(stmt_l)
    lesson = res_l.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    # Prevent removing primary course instructor via this route
    if lesson.teacher_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove primary course instructor. Please assign a replacement instructor first.",
        )

    res_del = await db.execute(
        delete(LessonMember).where(
            LessonMember.lesson_id == course_id,
            LessonMember.user_id == user_id,
        )
    )
    await db.commit()

    if res_del.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in course")

    return {"success": True, "message": "User removed from course successfully"}
