from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.features.lessons.models import Lesson
from .schemas import LessonTabResponse

router = APIRouter()

@router.get("/lesson-tabs", response_model=List[LessonTabResponse])
async def get_lesson_tabs(db: AsyncSession = Depends(get_db)):
    stmt = select(Lesson).where(Lesson.is_active == True).order_by(Lesson.created_at.asc())
    result = await db.execute(stmt)
    lessons = result.scalars().all()

    tabs = [
        LessonTabResponse(
            id="lessons",
            label="درس‌ها",
            labelFa="درس‌ها",
            labelEn="Lessons",
            active=True,
            unreadCount=0,
        )
    ]

    for l in lessons:
        tabs.append(
            LessonTabResponse(
                id=str(l.lesson_id),
                label=l.title,
                labelFa=l.title,
                labelEn=l.title,
                active=False,
                unreadCount=0,
            )
        )

    return tabs
