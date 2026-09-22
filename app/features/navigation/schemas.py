from typing import Optional
from pydantic import BaseModel

class LessonTabResponse(BaseModel):
    id: str
    label: str
    labelFa: str
    labelEn: str
    active: bool = False
    unreadCount: int = 0
