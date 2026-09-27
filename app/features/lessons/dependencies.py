# app/features/lessons/dependencies.py
import uuid
from fastapi import Path, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.features.users.models import User
from .repository import LessonRepository


async def require_lesson_teacher(
    lesson_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    repo = LessonRepository(db)
    lesson = await repo.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    u_type = (current_user.user_type or "").upper()
    if u_type in {"TEACHER", "ADMIN", "PROFESSOR", "INSTRUCTOR"} or lesson.teacher_id == current_user.user_id:
        return current_user
    raise HTTPException(status_code=403, detail="Teacher access required")


async def require_lesson_member(
    lesson_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    repo = LessonRepository(db)
    lesson = await repo.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    u_type = (current_user.user_type or "").upper()
    if u_type in {"TEACHER", "ADMIN", "PROFESSOR", "INSTRUCTOR"} or lesson.teacher_id == current_user.user_id:
        return current_user
    member = await repo.get_member(lesson_id, current_user.user_id)
    
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this lesson")
    
    return current_user