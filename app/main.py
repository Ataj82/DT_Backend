from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.api.router import api_router
from app.core.config import settings
from app.core.redis import init_redis, close_redis
from app.features.users.models import User
from app.features.chat.repository import ChatRepository

# Setup Static Directory
APP_DIR = Path(__file__).resolve().parent        
STATIC_DIR = (APP_DIR / "static").resolve()      
STATIC_DIR.mkdir(parents=True, exist_ok=True)    

# Initialize FastAPI
app = FastAPI(
    title="Fum Bot API", 
    description="Your custom Telegram-like API for AI bots",
    version="1.1", 
    root_path="/bot/v1", 
    docs_url=None,
    redoc_url=None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

UPLOAD_DIR = Path("uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 1. Public static serving ONLY for user avatars
AVATARS_DIR = (UPLOAD_DIR / "avatars").resolve()
AVATARS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=str(AVATARS_DIR)), name="avatars")
app.mount("/api/v1/uploads/avatars", StaticFiles(directory=str(AVATARS_DIR)), name="avatars_api")

# 2. Strict, authenticated & authorized file serving for chat attachments
@app.get("/uploads/chat/{filename:path}")
async def get_secure_chat_attachment(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clean_filename = Path(filename.strip("/")).name
    storage_key = f"uploads/chat/{clean_filename}"

    repo = ChatRepository(db)
    attachment = await repo.get_attachment_by_storage_key(storage_key)
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    # Resolve chat_id to verify chat membership
    chat_id = attachment.chat_id
    if not chat_id and attachment.message_id:
        msg = await repo.get_message_by_id(attachment.message_id)
        if msg:
            chat_id = msg.chat_id

    if chat_id:
        is_member = await repo.verify_active_membership(chat_id, current_user.user_id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this chat.",
            )
    else:
        # If chat_id is not yet associated, only allow the original uploader
        if attachment.uploader_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view this file.",
            )

    file_path = (UPLOAD_DIR / "chat" / clean_filename).resolve()
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk.",
        )

    return FileResponse(
        path=str(file_path),
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.file_name or clean_filename,
    )

@app.on_event("startup")
async def startup_event():
    print(f"[startup] Serving static from: {STATIC_DIR}")
    await init_redis()
    print("[startup] Redis connected.")
    try:
        from app.core.database import engine, Base
        import app.features.users.models
        import app.features.chat.models
        import app.features.lessons.models
        import app.features.auth.models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[startup] Database schema verified/created successfully.")
    except Exception as e:
        print(f"[startup] Warning: schema creation error: {e}")

    try:
        from app.core.seed import seed_database
        await seed_database()
        print("[startup] Seed database executed successfully.")
    except Exception as e:
        print(f"[startup] Warning: seed database skipped or error: {e}")

    try:
        from app.features.exam_pipeline.api.dependencies import get_framework
        from app.features.exam_pipeline.api.dependencies_multiuser import get_multiuser_service
        from app.features.exam_pipeline.api.routers.exam_requests import _sync_db_quizzes_to_pipeline
        from app.features.exam_pipeline.exceptions.handlers import register_exception_handlers
        fastapi_instance = globals()["app"]
        fw = get_framework()
        fastapi_instance.state.assessment_framework = fw
        register_exception_handlers(fastapi_instance)
        print("[startup] Adaptive exam pipeline framework initialized successfully.")

        svc = get_multiuser_service()
        await _sync_db_quizzes_to_pipeline(svc, fw)
        print("[startup] Synced DB quizzes into adaptive pipeline on startup.")
    except Exception as e:
        print(f"[startup] Warning: exam pipeline framework init error: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    await close_redis()
    print("[shutdown] Redis disconnected.")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/bot/v1/openapi.json",
        title=app.title + " - Swagger UI",
        oauth2_redirect_url="/bot/v1" + app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/bot/v1/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/bot/v1/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/bot/v1/static/swagger-ui/favicon-32x32.png",
    )

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

@app.get("/")
def read_root():
    return {"message": "Fum Bot API is running!"}

# Include API Router under /api/v1
app.include_router(api_router, prefix="/api/v1")

from uuid import UUID
from app.features.chat.router import (
    submit_message_feedback,
    add_message_comment,
    delete_message_comment,
    mark_message_comment_read,
    bulk_mark_comments_read,
    get_student_unread_comments_summary,
)
from app.features.chat.schemas import (
    MessageFeedbackRequest,
    MessageCommentCreate,
    MarkCommentReadRequest,
    BulkMarkCommentReadRequest,
)

@app.post("/api/v1/messages/{message_id}/feedback", tags=["Chats"])
async def message_feedback_alias(
    message_id: UUID,
    payload: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    return await submit_message_feedback(message_id, payload, db)

@app.post("/api/v1/messages/{message_id}/comments", tags=["Chats"])
async def message_comment_add_alias(
    message_id: UUID,
    payload: MessageCommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await add_message_comment(message_id, payload, request, db)

@app.delete("/api/v1/messages/{message_id}/comments/{comment_id}", tags=["Chats"])
async def message_comment_delete_alias(
    message_id: UUID,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await delete_message_comment(message_id, comment_id, db)

@app.post("/api/v1/messages/{message_id}/comments/{comment_id}/read", tags=["Chats"])
async def message_comment_read_alias(
    message_id: UUID,
    comment_id: str,
    payload: Optional[MarkCommentReadRequest] = None,
    student_id: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    return await mark_message_comment_read(message_id, comment_id, payload, student_id, request, db)

@app.post("/api/v1/messages/comments/mark-read", tags=["Chats"])
async def message_comment_bulk_read_alias(
    payload: BulkMarkCommentReadRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    return await bulk_mark_comments_read(payload, request, db)

@app.get("/api/v1/students/{student_id}/unread-comments-summary", tags=["Chats"])
async def student_unread_comments_summary_alias(
    student_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await get_student_unread_comments_summary(student_id, request=request, db=db)


# Quiz Explain Answer Alias
from app.features.lessons.schemas import QuizExplainAnswerRequest, QuizExplainAnswerResponse
from app.features.lessons.router import explain_quiz_answer

@app.post("/api/v1/quiz/explain-answer", response_model=QuizExplainAnswerResponse, tags=["Quizzes"])
@app.post("/api/v1/quizzes/explain-answer", response_model=QuizExplainAnswerResponse, tags=["Quizzes"])
async def quiz_explain_answer_alias(
    payload: QuizExplainAnswerRequest,
):
    return await explain_quiz_answer(payload)


