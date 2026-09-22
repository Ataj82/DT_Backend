from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class StudentResponse(BaseModel):
    id: UUID
    lessonId: Optional[UUID] = None
    title: str
    photo_url: Optional[str] = None
    preview: str = ""
    status: str = "online"
    statusFa: str = "آنلاین"
    statusEn: str = "Online"
    date: str
    unreadCount: int = 0
    blocked: bool = False

class BlockStudentRequest(BaseModel):
    blocked: bool
