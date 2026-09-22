# from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
# from sqlalchemy.ext.asyncio import AsyncSession
# import uuid

# from api.dependencies import get_db, get_current_user
# from app.features.users.models import User
# from features.bot.schemas import BotConfigCreate, BotConfigResponse, SendMessageRequest, SetWebhookRequest, LessonCreate, LessonResponse, BotSessionResponse
# from features.bot.services import BotService

# router = APIRouter()

# @router.post("/me/config", response_model=BotConfigResponse)
# async def setup_bot_config(
#     data: BotConfigCreate,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     if current_user.user_type != "BOT":
#         raise HTTPException(status_code=403, detail="Only users of type 'BOT' can have configurations.")
#     service = BotService(db)
#     return await service.register_bot_config(current_user.user_id, data)

# # ----------------------------------------------------
# # EXPOSED BOT APIs (Mimicking api.telegram.org)
# # e.g., /api/v1/bot/bot<TOKEN>/sendMessage
# # ----------------------------------------------------

# @router.post("/bot{token}/setWebhook")
# async def bot_api_set_webhook(token: str, request: SetWebhookRequest, db: AsyncSession = Depends(get_db)):
#     service = BotService(db)
#     return await service.set_webhook(token, request.url)

# @router.post("/bot{token}/sendMessage")
# async def bot_api_send_message(token: str, request: SendMessageRequest, db: AsyncSession = Depends(get_db)):
#     service = BotService(db)
#     msg = await service.send_message_from_bot(token, request.chat_id, request.text, request.content_type)
#     return {"status": "ok", "message_id": str(msg.message_id)}

# # ----------------------------------------------------
# # Session/Lesson routing
# # ----------------------------------------------------

# @router.post("/sessions/start/{join_link_hash}", response_model=BotSessionResponse)
# async def start_session(
#     join_link_hash: str,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     service = BotService(db)
#     return await service.start_bot_session(current_user.user_id, join_link_hash)

# @router.post("/lessons", response_model=LessonResponse)
# async def create_lesson(
#     data: LessonCreate,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     if current_user.user_type != "TEACHER":
#         raise HTTPException(status_code=403, detail="Only teachers can create lessons")
#     service = BotService(db)
#     return await service.create_lesson(current_user.user_id, data)
