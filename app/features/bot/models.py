import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
import sqlalchemy as sa
from app.core.database import Base

class BotConfig(Base):
    __tablename__ = "bot_configs"
    bot_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    api_token = Column(String, unique=True, index=True, nullable=False)
    webhook_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bot_user = relationship("User", foreign_keys=[bot_id])

# class Lesson(Base):
#     __tablename__ = "lessons"
#     lesson_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
#     teacher_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
#     bot_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
#     title = Column(String, nullable=False)
#     description = Column(Text, nullable=True)
#     join_link_hash = Column(String, unique=True, nullable=False, index=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

#     teacher = relationship("User", foreign_keys=[teacher_id], back_populates="lessons_taught")
#     bot_user = relationship("User", foreign_keys=[bot_user_id])
#     sessions = relationship("BotSession", back_populates="lesson")

# class BotSession(Base):
#     __tablename__ = "bot_sessions"
#     user_session_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
#     student_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
#     # lesson_id = Column(PG_UUID(as_uuid=True), ForeignKey("lessons.lesson_id", ondelete="CASCADE"), nullable=False)
#     # chat_id = Column(PG_UUID(as_uuid=True), ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False, unique=True)
#     progress_state = Column(JSONB, server_default='{}', nullable=False) 
#     score = Column(Integer, nullable=True)
#     started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
#     last_interacted_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
#     __table_args__ = (UniqueConstraint('student_id', 'lesson_id', name='uq_student_lesson_session'),)

#     student = relationship("User", foreign_keys=[student_id], back_populates="bot_sessions")
    # lesson = relationship("Lesson", back_populates="sessions")
    # chat = relationship("Chat", back_populates="bot_session")
