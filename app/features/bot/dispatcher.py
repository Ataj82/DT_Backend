import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import asyncio
from app.features.bot.models import BotConfig
from app.features.chat.models import ChatMember
import uuid

async def dispatch_webhook_to_bot(db: AsyncSession, chat_id: uuid.UUID, message_data: dict):
    """
    Checks if a bot is part of this chat. If so, and if they have a webhook, send the payload.
    """
    # 1. Find the bot in this chat
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id, ChatMember.role == "BOT")
    result = await db.execute(stmt)
    bot_user_id = result.scalar_one_or_none()
    
    if not bot_user_id:
        return

    # 2. Get Bot Config
    stmt = select(BotConfig).where(BotConfig.bot_id == bot_user_id)
    result = await db.execute(stmt)
    bot_config = result.scalar_one_or_none()

    if bot_config and bot_config.webhook_url:
        async with httpx.AsyncClient() as client:
            try:
                # Telegram-style payload
                payload = {
                    "update_id": hash(message_data.get("message_id", "1")), # Mock up update ID
                    "message": {
                        "message_id": message_data.get("message_id"),
                        "from": {"id": message_data.get("sender_id")},
                        "chat": {"id": str(chat_id), "type": "private"},
                        "date": message_data.get("created_at"),
                        "text": message_data.get("text_content"),
                        "content_type": message_data.get("content_type")
                    }
                }
                response = await client.post(bot_config.webhook_url, json=payload, timeout=5.0)
                print(f"[Webhook Dispatch] sent to {bot_config.webhook_url} - Status: {response.status_code}")
            except Exception as e:
                print(f"[Webhook Dispatch] Error: {e}")
