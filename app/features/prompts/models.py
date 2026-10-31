import sqlalchemy as sa
from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class LessonPromptConfig(Base):
    __tablename__ = "lesson_prompt_configs"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    lesson_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("lessons.lesson_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    prompt_type = Column(String(64), nullable=False, index=True)

    name = Column(String(255), nullable=True)
    name_fa = Column(String(255), nullable=True)
    category = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    description_fa = Column(Text, nullable=True)

    system_prompt = Column(Text, nullable=False)
    tone_and_style = Column(String(64), nullable=True)
    custom_rules = Column(JSONB, nullable=True, server_default=sa.text("'[]'::jsonb"))
    model_override = Column(String(128), nullable=True)

    is_active = Column(Boolean, nullable=False, server_default=sa.true(), default=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    lesson = relationship("Lesson", foreign_keys=[lesson_id])


class LessonPromptHistory(Base):
    __tablename__ = "lesson_prompt_history"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    lesson_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("lessons.lesson_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    prompt_type = Column(String(64), nullable=False, index=True)
    system_prompt = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    changed_by = Column(String(128), nullable=True, default="admin")
    change_summary = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lesson = relationship("Lesson", foreign_keys=[lesson_id])
