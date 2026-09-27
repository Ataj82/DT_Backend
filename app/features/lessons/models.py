from app.core.database import Base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
    Integer,
    BigInteger,
    UniqueConstraint,
    Index,
    func,
)
import sqlalchemy as sa
from sqlalchemy.orm import relationship
from app.features.chat.models import MessageAttachment


class Lesson(Base):
    __tablename__ = "lessons"

    lesson_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    subject = Column(String(128), nullable=True)
    avatar_url = Column(Text, nullable=True)
    
    teacher_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    bot_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    
    is_active = Column(Boolean, nullable=False, server_default=sa.true(), default=True)
    is_public = Column(Boolean, nullable=False, server_default=sa.false(), default=False)
    
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    teacher = relationship("User", foreign_keys=[teacher_id])
    bot_user = relationship("User", foreign_keys=[bot_user_id])
    members = relationship("LessonMember", back_populates="lesson", cascade="all, delete-orphan")
    materials = relationship("LessonMaterial", back_populates="lesson", cascade="all, delete-orphan")
    bot_chats = relationship("LessonBotChat", back_populates="lesson", cascade="all, delete-orphan")
    quizzes = relationship("LessonQuiz", back_populates="lesson", cascade="all, delete-orphan")

class LessonMember(Base):
    __tablename__ = "lesson_members"

    lesson_member_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    lesson_id = Column(PG_UUID(as_uuid=True), ForeignKey("lessons.lesson_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    
    role = Column(String(20), default="STUDENT", nullable=False)  # TEACHER, STUDENT
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)

    lesson = relationship("Lesson", back_populates="members")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("lesson_id", "user_id", name="uq_lesson_member"),)


class LessonMaterial(Base):
    __tablename__ = "lesson_materials"

    material_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    lesson_id = Column(PG_UUID(as_uuid=True), ForeignKey("lessons.lesson_id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    attachment_id = Column(
        PG_UUID(as_uuid=True), 
        ForeignKey("message_attachments.attachment_id", ondelete="SET NULL"), 
        nullable=True
    )
    
    rag_status = Column(String(64), nullable=True, server_default="ready")
    rag_metadata = Column(JSONB, nullable=True, server_default="{}")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lesson = relationship("Lesson", back_populates="materials")
    teacher = relationship("User")
    attachment = relationship("MessageAttachment")


class LessonBotChat(Base):
    __tablename__ = "lesson_bot_chats"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    lesson_id = Column(PG_UUID(as_uuid=True), ForeignKey("lessons.lesson_id", ondelete="CASCADE"), nullable=False)
    student_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    
    chat_id = Column(PG_UUID(as_uuid=True), ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False, unique=True)
    # bot_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lesson = relationship("Lesson", back_populates="bot_chats")
    student = relationship("User", foreign_keys=[student_id])
    chat = relationship("Chat", back_populates="lesson_bot_chat")
    # bot_user = relationship("User", foreign_keys=[bot_user_id])

    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_lesson_student_botchat"),
    )

class LessonQuiz(Base):
    __tablename__ = "lesson_quizzes"

    quiz_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    lesson_id = Column(PG_UUID(as_uuid=True), ForeignKey("lessons.lesson_id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Quiz configuration settings
    mode = Column(String(20), default="quiz")                    # quiz / regular
    is_anonymous = Column(Boolean, default=False)
    allows_multiple_answers = Column(Boolean, default=False)
    
    show_correct_after_answer = Column(Boolean, default=True)
    shuffle_questions = Column(Boolean, default=True)
    shuffle_options = Column(Boolean, default=True)
    
    duration_minutes = Column(Integer, nullable=True)
    max_attempts = Column(Integer, default=1)
    pass_score = Column(Integer, default=70)
    
    # Telegram Accordion & Exam Scheduling fields
    goals = Column(JSONB, nullable=True, server_default="[]")
    student_ids = Column(JSONB, nullable=True, server_default="[]")
    gap_minutes = Column(Integer, default=5, nullable=True)
    exam_date = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)
    start_at = Column(DateTime(timezone=True), nullable=True)
    end_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lesson = relationship("Lesson", back_populates="quizzes")
    questions = relationship("QuizQuestion", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", cascade="all, delete-orphan")

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    question_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    quiz_id = Column(PG_UUID(as_uuid=True), ForeignKey("lesson_quizzes.quiz_id", ondelete="CASCADE"), nullable=False)
    
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), default="MCQ")   # MCQ, TRUE_FALSE
    
    order = Column(Integer, nullable=False)
    points = Column(Integer, default=1)
    correct_explanation = Column(Text, nullable=True)
    
    quiz = relationship("LessonQuiz", back_populates="questions")
    options = relationship("QuestionOption", cascade="all, delete-orphan")


class QuestionOption(Base):
    __tablename__ = "question_options"

    option_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    question_id = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_questions.question_id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False, nullable=False)
    
    question = relationship("QuizQuestion", back_populates="options")

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    attempt_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    quiz_id = Column(PG_UUID(as_uuid=True), ForeignKey("lesson_quizzes.quiz_id", ondelete="CASCADE"), nullable=False)
    student_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    current_question_index = Column(Integer, default=0)   # Tracks progressive question index
    
    score = Column(Integer, default=0)
    correct_answers_count = Column(Integer, default=0)
    percentage = Column(Integer, nullable=True)
    passed = Column(Boolean, nullable=True)
    
    is_completed = Column(Boolean, default=False)
    is_abandoned = Column(Boolean, default=False)

    quiz = relationship("LessonQuiz", back_populates="attempts")
    student = relationship("User")
    answers = relationship("QuizAnswer", cascade="all, delete-orphan")

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    answer_id = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    attempt_id = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_attempts.attempt_id", ondelete="CASCADE"), nullable=False)
    question_id = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_questions.question_id", ondelete="CASCADE"), nullable=False)
    
    selected_option_id = Column(PG_UUID(as_uuid=True), ForeignKey("question_options.option_id"), nullable=True)
    text_answer = Column(Text, nullable=True)
    
    is_correct = Column(Boolean, nullable=True)
    score = Column(Integer, default=0)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())

    attempt = relationship("QuizAttempt", back_populates="answers")
    question = relationship("QuizQuestion")
    selected_option = relationship("QuestionOption")