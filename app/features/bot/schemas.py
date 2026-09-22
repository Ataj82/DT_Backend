# from pydantic import BaseModel, UUID4
# from typing import Optional, Dict, Any
# from datetime import datetime

# class BotConfigCreate(BaseModel):
#     webhook_url: Optional[str] = None

# class BotConfigResponse(BaseModel):
#     bot_id: UUID4
#     api_token: str
#     webhook_url: Optional[str]
#     created_at: datetime
    
#     class Config:
#         from_attributes = True

# class SetWebhookRequest(BaseModel):
#     url: str

# class SendMessageRequest(BaseModel):
#     chat_id: UUID4
#     text: str
#     content_type: str = "TEXT"

# class LessonCreate(BaseModel):
#     title: str
#     description: Optional[str] = None
#     join_link_hash: str
#     bot_user_id: UUID4

# class LessonResponse(BaseModel):
#     lesson_id: UUID4
#     teacher_id: UUID4
#     bot_user_id: UUID4
#     title: str
#     description: Optional[str]
#     join_link_hash: str
#     created_at: datetime
#     updated_at: datetime

#     class Config:
#         from_attributes = True

# class BotSessionCreate(BaseModel):
#     lesson_id: UUID4
#     student_id: UUID4
#     chat_id: UUID4

# class BotSessionResponse(BaseModel):
#     user_session_id: UUID4
#     student_id: UUID4
#     lesson_id: UUID4
#     chat_id: UUID4
#     progress_state: Dict[str, Any]
#     score: Optional[int]
#     started_at: datetime
#     last_interacted_at: datetime

#     class Config:
#         from_attributes = True
