# app/features/lessons/router.py
import uuid
from fastapi import APIRouter, Depends, status, Path, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.features.users.models import User
from .schemas import *
from .services import LessonService
from .dependencies import require_lesson_teacher, require_lesson_member

router = APIRouter()


def get_lesson_service(db: AsyncSession = Depends(get_db)) -> LessonService:
    return LessonService(db)


# ====================== Lesson ======================
@router.post("", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    payload: LessonCreate,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(get_current_user),
):
    return await service.create_lesson(current_user.user_id, payload)


@router.get("/my", response_model=List[LessonResponse])
async def get_my_lessons(
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(get_current_user),
):
    return await service.get_lessons(current_user.user_id)


@router.get("/{lesson_id}", response_model=LessonResponse, summary="نمایش اطلاعات درس")
async def get_lesson(
    lesson_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    lesson = await service.repo.get_lesson(lesson_id)
    return LessonResponse.model_validate(lesson)


# ====================== Members ======================
@router.get("/{lesson_id}/members", response_model=List[LessonMemberResponse], summary="نمایش لیست کاربران درس")
async def get_lesson_members(
    lesson_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    return await service.get_members(lesson_id)


@router.post("/{lesson_id}/members", response_model=List[LessonMemberResponse], summary="اضافه کردن کاربران به درس")
async def add_lesson_members(
    lesson_id: uuid.UUID,
    payload: LessonAddMembersRequest,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.add_members(lesson_id, payload)


# ====================== Materials ======================
@router.post("/{lesson_id}/materials/upload", response_model=LessonMaterialResponse, summary="آپلود جزوه جدید توسط استاد")
async def upload_material(
    lesson_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.upload_material(
        lesson_id=lesson_id,
        teacher_id=current_user.user_id,
        file=file,
        title=title,
        description=description,
    )


@router.post("/{lesson_id}/materials", response_model=LessonMaterialResponse, summary="ثبت متادیتای جزوه")
async def add_material(
    lesson_id: uuid.UUID,
    payload: LessonMaterialCreate,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.add_material(lesson_id, current_user.user_id, payload)


@router.get("/{lesson_id}/materials", response_model=List[LessonMaterialResponse], summary="دریافت لیست جزوات درس")
async def get_materials(
    lesson_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    return await service.get_materials(lesson_id)


@router.get("/{lesson_id}/materials/{material_id}/download", summary="دانلود امن فایل جزوه")
async def download_material_file(
    lesson_id: uuid.UUID,
    material_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    file_path, filename, media_type = await service.get_material_file(lesson_id, material_id)
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


@router.delete("/{lesson_id}/materials/{material_id}", summary="حذف جزوه توسط استاد")
async def delete_material(
    lesson_id: uuid.UUID,
    material_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.delete_material(lesson_id, material_id, current_user.user_id)


@router.post("/{lesson_id}/materials/{material_id}/rag-sync", response_model=LessonMaterialRagSyncResponse, summary="همگام‌سازی جزوه با بستر RAG")
async def sync_material_rag(
    lesson_id: uuid.UUID,
    material_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.sync_material_rag(lesson_id, material_id, current_user.user_id)


@router.get("/{lesson_id}/materials/{material_id}/rag-status", summary="استعلام وضعیت هوش مصنوعی / RAG جزوه")
async def get_material_rag_status(
    lesson_id: uuid.UUID,
    material_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    return await service.get_rag_status(lesson_id, material_id)


# ====================== Quiz ======================
@router.post("/{lesson_id}/quizzes", response_model=LessonQuizResponse)
async def create_quiz(
    lesson_id: uuid.UUID,
    payload: LessonQuizCreate,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.create_quiz(lesson_id, current_user.user_id, payload)


# ====================== Bot Chat ======================
@router.get("/{lesson_id}/students/{student_id}/bot-chat", response_model=LessonBotChatResponse, summary="نمایش بخش چت یک نفر با بات")
async def get_bot_chat(
    lesson_id: uuid.UUID,
    student_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    chat = await service.get_bot_chat_for_student(lesson_id, student_id)
    if not chat:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Bot chat not found")
    return chat

@router.post("/{lesson_id}/students/{student_id}/bot-chat/messages", summary="ارسال پیام توسط استاد در چت بات دانشجو")
async def send_message_to_student_bot_chat(
    lesson_id: uuid.UUID,
    student_id: uuid.UUID,
    payload: LessonBotChatMessageCreate,
    chat_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.send_message_for_teacher(
        lesson_id=lesson_id,
        chat_id=chat_id,
        sender_id=current_user.user_id,
        client_message_id=payload.client_message_id,
        content_type=payload.content_type,
        text_content=payload.text_content,
        metadata_json=payload.metadata_json,
        reply_to_message_id=payload.reply_to_message_id,
        attachment_ids=payload.attachment_ids,
        is_silent=payload.is_silent,
        scheduled_at=payload.scheduled_at,
    )

@router.get("/{lesson_id}/students/{student_id}/bot-chat/detail", summary="get_chat_of_student_for_teacher")
async def get_chat_of_student_for_teacher(
        lesson_id: uuid.UUID,
        student_id: uuid.UUID,
        service: LessonService = Depends(get_lesson_service),
        current_user: User = Depends(require_lesson_teacher),
):
    return await service.get_chat_detail_for_teacher(student_id, lesson_id)

@router.get("/{lesson_id}/students/{student_id}/bot-chat/state", summary="get_chat_status_of_student_for_teacher")
async def get_chat_status_of_student_for_teacher(
    lesson_id: uuid.UUID,
    student_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.get_user_chat_state_for_teacher(student_id, lesson_id)

@router.get("/{lesson_id}/students/{student_id}/bot-chat/messages", summary="get_messages_of_student_for_teacher")
async def get_messages_of_student_for_teacher(
    lesson_id: uuid.UUID,
    student_id: uuid.UUID,
    chat_id: uuid.UUID,
    limit: int = 50,
    before_message_id: Optional[uuid.UUID] = None,
    after_message_id: Optional[uuid.UUID] = None,
    around_message_id: Optional[uuid.UUID] = None,
    include_deleted: bool = False,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.get_messages_for_teacher(
        lesson_id=lesson_id, 
        chat_id=chat_id, 
        user_id=current_user.user_id,
        limit=limit,
        before_message_id=before_message_id,
        after_message_id=after_message_id,
        around_message_id=around_message_id,
        include_deleted=include_deleted
    )
@router.get("/{lesson_id}/quizzes", response_model=List[LessonQuizResponse])
async def get_quizzes(
    lesson_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    return await service.get_quizzes(lesson_id)

@router.post("/{lesson_id}/quizzes/{quiz_id}/questions", response_model=QuizQuestionResponse)
async def add_quiz_question(
    lesson_id: uuid.UUID,
    quiz_id: uuid.UUID,
    payload: QuizQuestionCreate,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.add_quiz_question(quiz_id, payload)

@router.get("/{lesson_id}/quizzes/{quiz_id}/questions", response_model=List[QuizQuestionResponse])
async def get_quiz_questions(
    lesson_id: uuid.UUID,
    quiz_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_member),
):
    return await service.get_quiz_questions(quiz_id)

@router.get("/{lesson_id}/quizzes/{quiz_id}/attempts", response_model=List[QuizAttemptListResponse], summary="نمایش نتایج آزمون برای استاد")
async def get_quiz_attempts(
    lesson_id: uuid.UUID,
    quiz_id: uuid.UUID,
    service: LessonService = Depends(get_lesson_service),
    current_user: User = Depends(require_lesson_teacher),
):
    return await service.get_quiz_attempts(quiz_id)
