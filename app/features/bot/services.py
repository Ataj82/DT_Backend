# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from fastapi import HTTPException
# import uuid
# import secrets

# from features.bot.repository import BotRepository
# from app.features.bot.models import BotConfig,Lesson
# from features.bot.schemas import LessonCreate, BotConfigCreate
# from features.chat.repository import ChatRepository
# from features.chat.services import manager
# import json

# class BotService:
#     def __init__(self, db: AsyncSession):
#         self.db = db
#         self.bot_repo = BotRepository(db)
#         self.chat_repo = ChatRepository(db)

#     async def get_bot_by_token(self, token: str) -> BotConfig | None:
#         stmt = select(BotConfig).where(BotConfig.api_token == token)
#         result = await self.db.execute(stmt)
#         return result.scalar_one_or_none()

#     async def register_bot_config(self, user_id: uuid.UUID, data: BotConfigCreate) -> BotConfig:
#         # Check if already exists
#         stmt = select(BotConfig).where(BotConfig.bot_id == user_id)
#         result = await self.db.execute(stmt)
#         existing = result.scalar_one_or_none()

#         if existing:
#             # Update webhook url
#             existing.webhook_url = data.webhook_url
#             await self.db.commit()
#             await self.db.refresh(existing)
#             return existing

#         # Generate a unique token mimicking Telegram
#         random_token = secrets.token_urlsafe(32)
#         new_config = BotConfig(
#             bot_id=user_id,
#             api_token=random_token,
#             webhook_url=data.webhook_url
#         )
#         self.db.add(new_config)
#         await self.db.commit()
#         await self.db.refresh(new_config)
#         return new_config

#     async def send_message_from_bot(self, token: str, chat_id: uuid.UUID, text: str, content_type: str = "TEXT"):
#         bot_config = await self.get_bot_by_token(token)
#         if not bot_config:
#             raise HTTPException(status_code=401, detail="Invalid bot token")
            
#         bot_id = bot_config.bot_id
        
#         # Verify bot is in chat
#         is_member = await self.chat_repo.verify_membership(chat_id, bot_id)
#         if not is_member:
#             raise HTTPException(status_code=403, detail="Bot is not a member of this chat")

#         # Save to DB
#         msg = await self.chat_repo.save_message(chat_id, bot_id, text, content_type)
        
#         # Broadcast to WS manager
#         broadcast_msg = {
#             "message_id": str(msg.message_id),
#             "sender_id": str(bot_id),
#             "content_type": content_type,
#             "text_content": text,
#             "created_at": msg.created_at.isoformat()
#         }
#         await manager.broadcast_to_chat(chat_id, json.dumps(broadcast_msg))
#         return msg

#     async def set_webhook(self, token: str, url: str):
#         bot_config = await self.get_bot_by_token(token)
#         if not bot_config:
#             raise HTTPException(status_code=401, detail="Invalid bot token")

#         bot_config.webhook_url = url
#         await self.db.commit()
#         return {"status": "ok", "message": "Webhook updated successfully"}

#     async def start_bot_session(self, student_id: uuid.UUID, join_link_hash: str):
#         lesson = await self.bot_repo.get_lesson_by_hash(join_link_hash)
#         if not lesson:
#             raise HTTPException(status_code=404, detail="Lesson not found")

#         chat = await self.chat_repo.create_chat(
#             chat_type="BOT_SESSION", 
#             title=f"Session: {lesson.title}"
#         )
        
#         await self.chat_repo.add_chat_member(chat.chat_id, student_id, role="STUDENT")
#         await self.chat_repo.add_chat_member(chat.chat_id, lesson.bot_user_id, role="BOT")
        
#         bot_session = await self.bot_repo.create_bot_session(
#             student_id=student_id,
#             lesson_id=lesson.lesson_id,
#             chat_id=chat.chat_id
#         )
#         return bot_session

#     async def create_lesson(self, teacher_id: uuid.UUID, data: LessonCreate):
#         lesson = Lesson(
#             teacher_id=teacher_id,
#             bot_user_id=data.bot_user_id,
#             title=data.title,
#             description=data.description,
#             join_link_hash=data.join_link_hash or secrets.token_urlsafe(8)
#         )
#         self.db.add(lesson)
#         await self.db.commit()
#         await self.db.refresh(lesson)
#         return lesson
