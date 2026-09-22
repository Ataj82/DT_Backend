# app/features/lessons/schemas.py
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ========================= Lesson =========================
class LessonCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    subject: Optional[str] = Field(None, max_length=128)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_public: bool = False


class LessonUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class LessonResponse(BaseModel):
    lesson_id: UUID
    title: str
    description: Optional[str]
    subject: Optional[str]
    teacher_id: UUID
    is_active: bool
    is_public: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========================= Member =========================
class MemberUserDetail(BaseModel):
    user_id: UUID
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)

class LessonMemberResponse(BaseModel):
    lesson_member_id: UUID
    user_id: UUID
    role: str  # TEACHER / STUDENT
    joined_at: datetime
    left_at: Optional[datetime]
    user: Optional[MemberUserDetail] = None

    model_config = ConfigDict(from_attributes=True)


class LessonAddMembersRequest(BaseModel):
    user_ids: List[UUID]


# ========================= Material =========================
class LessonMaterialCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    attachment_id: UUID


class LessonMaterialResponse(BaseModel):
    material_id: UUID
    title: str
    description: Optional[str] = None
    attachment_id: Optional[UUID] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    download_url: Optional[str] = None
    rag_status: Optional[str] = "ready"
    rag_metadata: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LessonMaterialRagSyncResponse(BaseModel):
    material_id: UUID
    status: str
    message: str
    rag_metadata: Optional[dict] = None


# ========================= Bot Chat =========================
class LessonBotChatMessageCreate(BaseModel):
    client_message_id: Optional[str] = None
    content_type: str = "TEXT"
    text_content: Optional[str] = None
    metadata_json: Optional[dict] = None
    reply_to_message_id: Optional[UUID] = None
    attachment_ids: List[UUID] = Field(default_factory=list)
    is_silent: bool = False
    scheduled_at: Optional[datetime] = None

class LessonBotChatResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    student_id: UUID
    bot_user_id: UUID
    chat_id: UUID
    
    model_config = ConfigDict(from_attributes=True)


# ========================= Quiz =========================
class LessonQuizCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    mode: str = Field("quiz", pattern="^(quiz|regular)$")
    show_correct_after_answer: bool = True
    shuffle_questions: bool = True
    shuffle_options: bool = True
    duration_minutes: Optional[int] = Field(None, gt=0)
    max_attempts: int = Field(1, ge=1)
    pass_score: int = Field(70, ge=0, le=100)


class LessonQuizResponse(BaseModel):
    quiz_id: UUID
    title: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========================= Attempt =========================
class QuizAttemptResponse(BaseModel):
    attempt_id: UUID
    quiz_id: UUID
    student_id: UUID
    started_at: datetime
    completed_at: Optional[datetime]
    score: int = 0
    percentage: Optional[float]
    passed: Optional[bool]
    is_completed: bool = False
    current_question_index: int = 0

    model_config = ConfigDict(from_attributes=True)
# ========================= Quiz Questions =========================
class QuestionOptionCreate(BaseModel):
    text: str
    is_correct: bool = False

class QuizQuestionCreate(BaseModel):
    question_text: str = Field(..., max_length=2000)
    question_type: str = Field("MCQ", pattern="^(MCQ|TRUE_FALSE)$")
    order: int
    points: int = 1
    correct_explanation: Optional[str] = None
    options: List[QuestionOptionCreate] = Field(default_factory=list)

class QuestionOptionResponse(BaseModel):
    option_id: UUID
    text: str
    is_correct: bool

    model_config = ConfigDict(from_attributes=True)

class QuizQuestionResponse(BaseModel):
    question_id: UUID
    quiz_id: UUID
    question_text: str
    question_type: str
    order: int
    points: int
    correct_explanation: Optional[str]
    options: List[QuestionOptionResponse] = []

    model_config = ConfigDict(from_attributes=True)

class QuizAttemptListResponse(BaseModel):
    attempt_id: UUID
    quiz_id: UUID
    student_id: UUID
    student: Optional[MemberUserDetail] = None
    started_at: datetime
    completed_at: Optional[datetime]
    score: int
    percentage: Optional[float]
    passed: Optional[bool]
    is_completed: bool

    model_config = ConfigDict(from_attributes=True)
