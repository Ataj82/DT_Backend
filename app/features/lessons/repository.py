# app/features/lessons/repository.py
from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.features.lessons.models import (
    Lesson, LessonMember, LessonMaterial,
    LessonBotChat, LessonQuiz
)


class LessonRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Lesson
    async def create(self, teacher_id: UUID, **data) -> Lesson:
        lesson = Lesson(teacher_id=teacher_id, **data)
        self.db.add(lesson)
        await self.db.commit()
        await self.db.refresh(lesson)
        return lesson

    async def get_lesson_member(self, user_id:UUID) -> List[Lesson]:
        stmt = (
            select(Lesson)
            .join(Lesson.members)
            .where(
                LessonMember.user_id == user_id,
                LessonMember.left_at.is_(None)
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_lesson(self, lesson_id: UUID) -> Optional[Lesson]:
        stmt = select(Lesson).where(Lesson.lesson_id == lesson_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_teacher_lessons(self, teacher_id: UUID) -> List[Lesson]:
        stmt = select(Lesson).where(
            Lesson.teacher_id == teacher_id,
            Lesson.is_active == True
        ).order_by(Lesson.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Member
    async def add_member(self, lesson_id: UUID, user_id: UUID, role: str = "STUDENT"):
        member = LessonMember(lesson_id=lesson_id, user_id=user_id, role=role)
        self.db.add(member)
        await self.db.commit()

    async def get_member(self, lesson_id: UUID, user_id: UUID) -> Optional[LessonMember]:
        stmt = select(LessonMember).where(
            LessonMember.lesson_id == lesson_id,
            LessonMember.user_id == user_id,
            LessonMember.left_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_members(self, lesson_id: UUID) -> List[LessonMember]:
        from sqlalchemy.orm import selectinload
        stmt = select(LessonMember).options(selectinload(LessonMember.user)).where(
            LessonMember.lesson_id == lesson_id,
            LessonMember.left_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Material
    async def add_material(self, **kwargs) -> LessonMaterial:
        material = LessonMaterial(**kwargs)
        self.db.add(material)
        await self.db.commit()
        await self.db.refresh(material)
        return material

    async def get_materials(self, lesson_id: UUID) -> List[LessonMaterial]:
        from sqlalchemy.orm import selectinload
        stmt = (
            select(LessonMaterial)
            .options(selectinload(LessonMaterial.attachment))
            .where(LessonMaterial.lesson_id == lesson_id)
            .order_by(LessonMaterial.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_material(self, lesson_id: UUID, material_id: UUID) -> Optional[LessonMaterial]:
        from sqlalchemy.orm import selectinload
        stmt = (
            select(LessonMaterial)
            .options(selectinload(LessonMaterial.attachment))
            .where(
                LessonMaterial.lesson_id == lesson_id,
                LessonMaterial.material_id == material_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_material(self, material: LessonMaterial) -> None:
        await self.db.delete(material)
        await self.db.commit()

    async def update_material(self, material: LessonMaterial) -> LessonMaterial:
        await self.db.commit()
        await self.db.refresh(material)
        return material

    # Bot Chat
    async def create_bot_chat(self, **kwargs) -> LessonBotChat:
        bot_chat = LessonBotChat(**kwargs)
        self.db.add(bot_chat)
        await self.db.commit()
        await self.db.refresh(bot_chat)
        return bot_chat

    async def get_bot_chat(self, lesson_id: UUID, student_id: UUID) -> Optional[LessonBotChat]:
        stmt = select(LessonBotChat).where(
            LessonBotChat.lesson_id == lesson_id,
            LessonBotChat.student_id == student_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # Quiz
    async def create_quiz(self, **kwargs) -> LessonQuiz:
        quiz = LessonQuiz(**kwargs)
        self.db.add(quiz)
        await self.db.commit()
        await self.db.refresh(quiz)
        return quiz
    async def get_quizzes(self, lesson_id: UUID) -> List[LessonQuiz]:
        stmt = select(LessonQuiz).where(LessonQuiz.lesson_id == lesson_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Quiz Questions
    async def create_quiz_question(self, quiz_id: UUID, **kwargs) -> "QuizQuestion":
        from app.features.lessons.models import QuizQuestion, QuestionOption
        options_data = kwargs.pop("options", [])
        question = QuizQuestion(quiz_id=quiz_id, **kwargs)
        self.db.add(question)
        await self.db.flush()
        
        for opt in options_data:
            option = QuestionOption(question_id=question.question_id, **opt.model_dump())
            self.db.add(option)
            
        await self.db.commit()
        await self.db.refresh(question)
        return question

    async def get_quiz_questions(self, quiz_id: UUID) -> List["QuizQuestion"]:
        from sqlalchemy.orm import selectinload
        from app.features.lessons.models import QuizQuestion
        stmt = select(QuizQuestion).options(selectinload(QuizQuestion.options)).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.order)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Quiz Attempts
    async def get_quiz_attempts(self, quiz_id: UUID) -> List["QuizAttempt"]:
        from sqlalchemy.orm import selectinload
        from app.features.lessons.models import QuizAttempt
        stmt = select(QuizAttempt).options(selectinload(QuizAttempt.student)).where(QuizAttempt.quiz_id == quiz_id).order_by(QuizAttempt.started_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
