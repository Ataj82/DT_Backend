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


# ====================== Quiz AI Explanation ======================
@router.post(
    "/quizzes/explain-answer",
    response_model=QuizExplainAnswerResponse,
    summary="توضیح تحلیلی و جامع پاسخ سوال کوییز با هوش مصنوعی",
)
async def explain_quiz_answer(
    payload: QuizExplainAnswerRequest,
):
    """
    ارسال پرامپت آماده به سرور مدل زبانی (Qwen در http://94.184.177.171:8000/v1)
    و تولید یک پاسخنامه تحلیلی و آموزشی جامع به زبان فارسی.
    """
    import asyncio
    from app.features.exam_pipeline.llm.provider import LLMProvider
    from app.features.exam_pipeline.configuration.llm_configuration import LLMConfiguration

    # Build options text if available
    options_text = ""
    if payload.options and isinstance(payload.options, list):
        formatted_list = []
        labels = ["الف", "ب", "ج", "د", "هـ"]
        for idx, opt in enumerate(payload.options):
            lbl = labels[idx] if idx < len(labels) else f"گزینه {idx+1}"
            if isinstance(opt, dict):
                text = opt.get("text") or opt.get("answer") or str(opt)
                formatted_list.append(f"{lbl}) {text}")
            else:
                formatted_list.append(f"{lbl}) {opt}")
        options_text = "\n".join(formatted_list)

    system_prompt = (
        "شما یک استاد دانشگاه و متخصص آموزشی با تجربه و مسلط هستید.\n"
        "وظیفه شما تحلیل دقیق و تشریحی سوال آزمون و ارائه یک پاسخنامه تحلیلی، مستدل، آموزنده و جامع به زبان فارسی است.\n"
        "پاسخ باید ساختاریافته، بسیار روان، علمی و با رعایت نکات نگارشی فارسی باشد."
    )

    user_parts = [
        "لطفاً سوال آزمون چهارگزینه‌ای زیر را به شکل کامل و جامع تشریح و تحلیل کنید:\n",
        f"**صورت سوال:**\n{payload.question}\n",
    ]

    if options_text:
        user_parts.append(f"**گزینه‌ها:**\n{options_text}\n")

    if payload.answer is not None and str(payload.answer).strip():
        user_parts.append(f"**پاسخ صحیح اعلام‌شده:** {payload.answer}\n")

    if payload.selected_answer is not None and str(payload.selected_answer).strip():
        user_parts.append(f"**پاسخ انتخابی دانشجو:** {payload.selected_answer}\n")

    user_parts.append(
        "لطفاً پاسخ را در قالبی کاملاً ساختاریافته و با عناوین زیر ارائه دهید:\n\n"
        "۱. **پاسخ صحیح و استدلال علمی:**\n"
        "گزینه یا پاسخ درست را مشخص کرده و منطق علمی و مستدل پشت آن را به طور کامل توضیح دهید.\n\n"
        "۲. **تحلیل و رد سایر گزینه‌ها:**\n"
        "سایر گزینه‌ها را به تفکیک بررسی کنید و علت نادرست بودن یا تله مفهومی آن‌ها را مشخص کنید.\n\n"
        "۳. **نکته کلیدی آموزشی:**\n"
        "یک جمع‌بندی مفهومی یا نکته مهم امتحانی مرتبط با این مبحث برای یادگیری عمیق‌تر ارائه دهید."
    )

    if (
        payload.selected_answer is not None
        and payload.answer is not None
        and str(payload.selected_answer).strip() != str(payload.answer).strip()
    ):
        user_parts.append(
            "\n۴. **علت اشتباه احتمالی دانشجو:**\n"
            "دلیل انتخاب این گزینه نادرست توسط دانشجو و کج‌فهمی رایج در این زمینه را توضیح دهید."
        )

    user_prompt = "\n".join(user_parts)

    try:
        llm_cfg = LLMConfiguration.from_env()
        # Set appropriate parameters for comprehensive analytical explanation
        if llm_cfg.max_tokens < 1200:
            llm_cfg = LLMConfiguration(
                provider=llm_cfg.provider,
                model=llm_cfg.model,
                temperature=0.3,
                max_tokens=1500,
                timeout_seconds=30,
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
            )

        llm = LLMProvider(configuration=llm_cfg)
        explanation = await asyncio.to_thread(
            llm.chat,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return QuizExplainAnswerResponse(explanation=explanation.strip())
    except Exception as e:
        return QuizExplainAnswerResponse(
            explanation=f"در حال حاضر امکان دریافت تحلیل هوش مصنوعی وجود ندارد: {str(e)}"
        )
