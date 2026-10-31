from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.features.prompts.schemas import (
    PromptConfigResponse,
    PromptConfigUpdate,
    PromptHistoryItem,
    PromptListResponse,
)
from app.features.prompts.service import PromptService

router = APIRouter()


@router.get("", response_model=PromptListResponse)
async def get_prompts(
    lesson_id: Optional[UUID] = Query(
        None, description="شناسه درس برای دریافت پرامپت‌های اختصاصی آن درس"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    دریافت لیست تمامی پرامپت‌ها.
    در صورت ارسال lesson_id، پرامپت‌های اختصاصی آن درس به همراه وضعیت override برگردانده می‌شود.
    """
    return await PromptService.get_prompts(db=db, lesson_id=lesson_id)


@router.get("/{prompt_type}/history", response_model=List[PromptHistoryItem])
async def get_prompt_history(
    prompt_type: str,
    lesson_id: Optional[UUID] = Query(
        None, description="شناسه درس برای دریافت سوابق پرامپت اختصاصی"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    دریافت سوابق تغییرات پرامپت (نسخه‌بندی و لاگ تغییرات)
    """
    return await PromptService.get_history(
        db=db,
        prompt_type=prompt_type,
        lesson_id=lesson_id,
    )


@router.post("/{prompt_type}/rollback/{history_id}", response_model=PromptConfigResponse)
async def rollback_prompt(
    prompt_type: str,
    history_id: UUID,
    lesson_id: Optional[UUID] = Query(
        None, description="شناسه درس برای بازگردانی پرامپت اختصاصی"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    بازگردانی پرامپت به نسخه مشخصی از سوابق
    """
    return await PromptService.rollback_prompt(
        db=db,
        prompt_type=prompt_type,
        history_id=history_id,
        lesson_id=lesson_id,
    )


@router.put("/{prompt_type}", response_model=PromptConfigResponse)
async def update_prompt(
    prompt_type: str,
    payload: PromptConfigUpdate,
    lesson_id: Optional[UUID] = Query(
        None, description="شناسه درس برای ذخیره پرامپت اختصاصی"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    ذخیره و به‌روزرسانی متن پرامپت برای یک درس مشخص یا پیش‌فرض سراسری سیستم.
    """
    return await PromptService.update_prompt(
        db=db,
        prompt_type=prompt_type,
        payload=payload,
        lesson_id=lesson_id,
    )


@router.delete("/{prompt_type}/reset", response_model=PromptConfigResponse)
async def reset_prompt(
    prompt_type: str,
    lesson_id: Optional[UUID] = Query(
        None, description="شناسه درس برای بازنشانی پرامپت به پیش‌فرض"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    بازنشانی پرامپت اختصاصی درس به حالت پیش‌فرض سراسری سیستم.
    """
    return await PromptService.reset_prompt(
        db=db,
        prompt_type=prompt_type,
        lesson_id=lesson_id,
    )

