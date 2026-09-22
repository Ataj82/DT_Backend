# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from sqlalchemy import update, Text
# from app.features.bot.models import Lesson, BotSession
# import uuid

# class BotRepository:
#     def __init__(self, session: AsyncSession):
#         self.session = session

#     async def create_lesson(self, teacher_id: uuid.UUID, title: str, join_link_hash: str, bot_user_id: uuid.UUID, description: str | None = None) -> Lesson:
#         lesson = Lesson(
#             teacher_id=teacher_id, 
#             bot_user_id=bot_user_id, 
#             title=title, 
#             description=description, 
#             join_link_hash=join_link_hash
#         )
#         self.session.add(lesson)
#         await self.session.commit()
#         await self.session.refresh(lesson)
#         return lesson

#     async def get_lesson_by_hash(self, join_link_hash: str) -> Lesson | None:
#         stmt = select(Lesson).where(Lesson.join_link_hash == join_link_hash)
#         result = await self.session.execute(stmt)
#         return result.scalar_one_or_none()

#     async def get_lesson_by_id(self, lesson_id: uuid.UUID) -> Lesson | None:
#         stmt = select(Lesson).where(Lesson.lesson_id == lesson_id)
#         result = await self.session.execute(stmt)
#         return result.scalar_one_or_none()

#     async def create_bot_session(self, student_id: uuid.UUID, lesson_id: uuid.UUID, chat_id: uuid.UUID) -> BotSession:
#         bot_session = BotSession(
#             student_id=student_id,
#             lesson_id=lesson_id,
#             chat_id=chat_id,
#             progress_state={"step": "START"}
#         )
#         self.session.add(bot_session)
#         await self.session.commit()
#         await self.session.refresh(bot_session)
#         return bot_session

#     async def get_bot_session(self, chat_id: uuid.UUID) -> BotSession | None:
#         stmt = select(BotSession).where(BotSession.chat_id == chat_id)
#         result = await self.session.execute(stmt)
#         return result.scalar_one_or_none()

#     async def update_bot_session(self, user_session_id: uuid.UUID, progress_state: dict, score: int | None = None) -> BotSession | None:
#         stmt = (
#             update(BotSession)
#             .where(BotSession.user_session_id == user_session_id)
#             .values(progress_state=progress_state, score=score)
#             .returning(BotSession)
#         )
#         result = await self.session.execute(stmt)
#         await self.session.commit()
#         return result.scalar_one_or_none()

