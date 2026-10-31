from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class PromptParameter(BaseModel):
    name: str
    label: str
    description: Optional[str] = None


class PromptConfigResponse(BaseModel):
    id: Optional[UUID] = None
    prompt_type: str
    name: str
    name_fa: str
    category: str
    source_file: Optional[str] = None
    description: Optional[str] = None
    description_fa: Optional[str] = None
    parameters: List[PromptParameter] = Field(default_factory=list)
    content: str
    default_content: str
    is_overridden: bool = False
    version: int = 1
    tone_and_style: Optional[str] = None
    custom_rules: List[str] = Field(default_factory=list)
    model_override: Optional[str] = None
    is_active: bool = True
    updated_at: Optional[datetime] = None
    lesson_id: Optional[UUID] = None


class PromptConfigUpdate(BaseModel):
    content: str = Field(..., min_length=10, description="متن پرامپت سیستم")
    change_summary: Optional[str] = Field(
        default="ویرایش و به‌روزرسانی دستورالعمل", description="توضیح کوتاه تغییر برای ثبت در سابقه"
    )
    changed_by: Optional[str] = Field(
        default="admin", description="نام کاربر یا نقش ثبت‌کننده تغییر"
    )
    tone_and_style: Optional[str] = None
    custom_rules: Optional[List[str]] = None
    model_override: Optional[str] = None
    is_active: Optional[bool] = True


class PromptHistoryItem(BaseModel):
    id: UUID
    lesson_id: Optional[UUID] = None
    prompt_type: str
    system_prompt: str
    version: int
    changed_by: Optional[str] = None
    change_summary: Optional[str] = None
    created_at: datetime


class PromptListResponse(BaseModel):
    scope: str  # "global" or "lesson"
    lesson_id: Optional[UUID] = None
    lesson_title: Optional[str] = None
    prompts: List[PromptConfigResponse]
