import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.features.lessons.models import Lesson
from app.features.prompts.models import LessonPromptConfig, LessonPromptHistory
from app.features.prompts.defaults import DEFAULT_PROMPTS
from app.features.prompts.schemas import (
    PromptConfigResponse,
    PromptConfigUpdate,
    PromptHistoryItem,
    PromptListResponse,
    PromptParameter,
)

logger = logging.getLogger("prompts_service")


class PromptService:
    @staticmethod
    async def get_prompts(
        db: AsyncSession, lesson_id: Optional[UUID] = None
    ) -> PromptListResponse:
        lesson_title = None

        if lesson_id:
            lesson_res = await db.execute(
                select(Lesson).where(
                    and_(Lesson.lesson_id == lesson_id, Lesson.deleted_at.is_(None))
                )
            )
            lesson = lesson_res.scalar_one_or_none()
            if not lesson:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="درس مورد نظر یافت نشد.",
                )
            lesson_title = lesson.title

            # Fetch lesson-level configurations
            lesson_configs_res = await db.execute(
                select(LessonPromptConfig).where(
                    LessonPromptConfig.lesson_id == lesson_id
                )
            )
            lesson_configs = {
                cfg.prompt_type: cfg for cfg in lesson_configs_res.scalars().all()
            }

            # Fetch global overrides as fallback
            global_configs_res = await db.execute(
                select(LessonPromptConfig).where(
                    LessonPromptConfig.lesson_id.is_(None)
                )
            )
            global_configs = {
                cfg.prompt_type: cfg for cfg in global_configs_res.scalars().all()
            }

            prompt_items: List[PromptConfigResponse] = []
            for p_type, default_info in DEFAULT_PROMPTS.items():
                params = [
                    PromptParameter(**p) for p in default_info.get("parameters", [])
                ]

                # Get latest version from history
                v_res = await db.execute(
                    select(func.max(LessonPromptHistory.version)).where(
                        and_(
                            LessonPromptHistory.lesson_id == lesson_id,
                            LessonPromptHistory.prompt_type == p_type,
                        )
                    )
                )
                curr_version = v_res.scalar() or 1

                if p_type in lesson_configs:
                    cfg = lesson_configs[p_type]
                    prompt_items.append(
                        PromptConfigResponse(
                            id=cfg.id,
                            prompt_type=p_type,
                            name=cfg.name or default_info["name"],
                            name_fa=cfg.name_fa or default_info["nameFa"],
                            category=cfg.category or default_info["category"],
                            source_file=default_info.get("source_file"),
                            description=cfg.description or default_info["description"],
                            description_fa=cfg.description_fa or default_info["descriptionFa"],
                            parameters=params,
                            content=cfg.system_prompt,
                            default_content=default_info["content"],
                            is_overridden=True,
                            version=curr_version,
                            tone_and_style=cfg.tone_and_style,
                            custom_rules=cfg.custom_rules or [],
                            model_override=cfg.model_override,
                            is_active=cfg.is_active,
                            updated_at=cfg.updated_at,
                            lesson_id=lesson_id,
                        )
                    )
                elif p_type in global_configs:
                    g_cfg = global_configs[p_type]
                    prompt_items.append(
                        PromptConfigResponse(
                            id=None,
                            prompt_type=p_type,
                            name=default_info["name"],
                            name_fa=default_info["nameFa"],
                            category=default_info["category"],
                            source_file=default_info.get("source_file"),
                            description=default_info["description"],
                            description_fa=default_info["descriptionFa"],
                            parameters=params,
                            content=g_cfg.system_prompt,
                            default_content=default_info["content"],
                            is_overridden=False,
                            version=curr_version,
                            tone_and_style=g_cfg.tone_and_style,
                            custom_rules=g_cfg.custom_rules or [],
                            model_override=g_cfg.model_override,
                            is_active=g_cfg.is_active,
                            updated_at=g_cfg.updated_at,
                            lesson_id=lesson_id,
                        )
                    )
                else:
                    prompt_items.append(
                        PromptConfigResponse(
                            id=None,
                            prompt_type=p_type,
                            name=default_info["name"],
                            name_fa=default_info["nameFa"],
                            category=default_info["category"],
                            source_file=default_info.get("source_file"),
                            description=default_info["description"],
                            description_fa=default_info["descriptionFa"],
                            parameters=params,
                            content=default_info["content"],
                            default_content=default_info["content"],
                            is_overridden=False,
                            version=1,
                            tone_and_style=None,
                            custom_rules=[],
                            model_override=None,
                            is_active=True,
                            updated_at=None,
                            lesson_id=lesson_id,
                        )
                    )

            return PromptListResponse(
                scope="lesson",
                lesson_id=lesson_id,
                lesson_title=lesson_title,
                prompts=prompt_items,
            )

        # Global scope
        global_res = await db.execute(
            select(LessonPromptConfig).where(LessonPromptConfig.lesson_id.is_(None))
        )
        global_configs = {
            cfg.prompt_type: cfg for cfg in global_res.scalars().all()
        }

        prompt_items = []
        for p_type, default_info in DEFAULT_PROMPTS.items():
            params = [
                PromptParameter(**p) for p in default_info.get("parameters", [])
            ]

            v_res = await db.execute(
                select(func.max(LessonPromptHistory.version)).where(
                    and_(
                        LessonPromptHistory.lesson_id.is_(None),
                        LessonPromptHistory.prompt_type == p_type,
                    )
                )
            )
            curr_version = v_res.scalar() or 1

            if p_type in global_configs:
                cfg = global_configs[p_type]
                prompt_items.append(
                    PromptConfigResponse(
                        id=cfg.id,
                        prompt_type=p_type,
                        name=cfg.name or default_info["name"],
                        name_fa=cfg.name_fa or default_info["nameFa"],
                        category=cfg.category or default_info["category"],
                        source_file=default_info.get("source_file"),
                        description=cfg.description or default_info["description"],
                        description_fa=cfg.description_fa or default_info["descriptionFa"],
                        parameters=params,
                        content=cfg.system_prompt,
                        default_content=default_info["content"],
                        is_overridden=True,
                        version=curr_version,
                        tone_and_style=cfg.tone_and_style,
                        custom_rules=cfg.custom_rules or [],
                        model_override=cfg.model_override,
                        is_active=cfg.is_active,
                        updated_at=cfg.updated_at,
                        lesson_id=None,
                    )
                )
            else:
                prompt_items.append(
                    PromptConfigResponse(
                        id=None,
                        prompt_type=p_type,
                        name=default_info["name"],
                        name_fa=default_info["nameFa"],
                        category=default_info["category"],
                        source_file=default_info.get("source_file"),
                        description=default_info["description"],
                        description_fa=default_info["descriptionFa"],
                        parameters=params,
                        content=default_info["content"],
                        default_content=default_info["content"],
                        is_overridden=False,
                        version=1,
                        tone_and_style=None,
                        custom_rules=[],
                        model_override=None,
                        is_active=True,
                        updated_at=None,
                        lesson_id=None,
                    )
                )

        return PromptListResponse(
            scope="global",
            lesson_id=None,
            lesson_title="تنظیمات پیش‌فرض سراسری سامانه",
            prompts=prompt_items,
        )

    @staticmethod
    async def update_prompt(
        db: AsyncSession,
        prompt_type: str,
        payload: PromptConfigUpdate,
        lesson_id: Optional[UUID] = None,
    ) -> PromptConfigResponse:
        default_info = DEFAULT_PROMPTS.get(prompt_type)
        if not default_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"نوع پرامپت '{prompt_type}' نامعتبر است.",
            )

        if lesson_id:
            lesson_check = await db.execute(
                select(Lesson).where(
                    and_(Lesson.lesson_id == lesson_id, Lesson.deleted_at.is_(None))
                )
            )
            if not lesson_check.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="درس مورد نظر یافت نشد.",
                )

            stmt = select(LessonPromptConfig).where(
                and_(
                    LessonPromptConfig.lesson_id == lesson_id,
                    LessonPromptConfig.prompt_type == prompt_type,
                )
            )
            v_stmt = select(func.max(LessonPromptHistory.version)).where(
                and_(
                    LessonPromptHistory.lesson_id == lesson_id,
                    LessonPromptHistory.prompt_type == prompt_type,
                )
            )
        else:
            stmt = select(LessonPromptConfig).where(
                and_(
                    LessonPromptConfig.lesson_id.is_(None),
                    LessonPromptConfig.prompt_type == prompt_type,
                )
            )
            v_stmt = select(func.max(LessonPromptHistory.version)).where(
                and_(
                    LessonPromptHistory.lesson_id.is_(None),
                    LessonPromptHistory.prompt_type == prompt_type,
                )
            )

        # Calculate version
        v_res = await db.execute(v_stmt)
        max_v = v_res.scalar() or 0
        new_version = max_v + 1

        res = await db.execute(stmt)
        existing_cfg = res.scalar_one_or_none()

        cleaned_content = payload.content.strip()

        if existing_cfg:
            existing_cfg.system_prompt = cleaned_content
            if payload.tone_and_style is not None:
                existing_cfg.tone_and_style = payload.tone_and_style
            if payload.custom_rules is not None:
                existing_cfg.custom_rules = payload.custom_rules
            if payload.model_override is not None:
                existing_cfg.model_override = payload.model_override
            if payload.is_active is not None:
                existing_cfg.is_active = payload.is_active
            cfg = existing_cfg
        else:
            cfg = LessonPromptConfig(
                lesson_id=lesson_id,
                prompt_type=prompt_type,
                name=default_info["name"],
                name_fa=default_info["nameFa"],
                category=default_info["category"],
                description=default_info["description"],
                description_fa=default_info["descriptionFa"],
                system_prompt=cleaned_content,
                tone_and_style=payload.tone_and_style,
                custom_rules=payload.custom_rules if payload.custom_rules is not None else [],
                model_override=payload.model_override,
                is_active=payload.is_active if payload.is_active is not None else True,
            )
            db.add(cfg)

        # Log into history table for full traceability
        history_entry = LessonPromptHistory(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            system_prompt=cleaned_content,
            version=new_version,
            changed_by=payload.changed_by or "admin",
            change_summary=payload.change_summary or "ویرایش و ذخیره دستورالعمل",
        )
        db.add(history_entry)

        await db.commit()
        await db.refresh(cfg)

        params = [
            PromptParameter(**p) for p in default_info.get("parameters", [])
        ]

        return PromptConfigResponse(
            id=cfg.id,
            prompt_type=cfg.prompt_type,
            name=cfg.name or default_info["name"],
            name_fa=cfg.name_fa or default_info["nameFa"],
            category=cfg.category or default_info["category"],
            source_file=default_info.get("source_file"),
            description=cfg.description or default_info["description"],
            description_fa=cfg.description_fa or default_info["descriptionFa"],
            parameters=params,
            content=cfg.system_prompt,
            default_content=default_info["content"],
            is_overridden=True,
            version=new_version,
            tone_and_style=cfg.tone_and_style,
            custom_rules=cfg.custom_rules or [],
            model_override=cfg.model_override,
            is_active=cfg.is_active,
            updated_at=cfg.updated_at,
            lesson_id=cfg.lesson_id,
        )

    @staticmethod
    async def get_history(
        db: AsyncSession, prompt_type: str, lesson_id: Optional[UUID] = None
    ) -> List[PromptHistoryItem]:
        default_info = DEFAULT_PROMPTS.get(prompt_type)
        if not default_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"نوع پرامپت '{prompt_type}' نامعتبر است.",
            )

        if lesson_id:
            stmt = (
                select(LessonPromptHistory)
                .where(
                    and_(
                        LessonPromptHistory.lesson_id == lesson_id,
                        LessonPromptHistory.prompt_type == prompt_type,
                    )
                )
                .order_by(desc(LessonPromptHistory.created_at))
            )
        else:
            stmt = (
                select(LessonPromptHistory)
                .where(
                    and_(
                        LessonPromptHistory.lesson_id.is_(None),
                        LessonPromptHistory.prompt_type == prompt_type,
                    )
                )
                .order_by(desc(LessonPromptHistory.created_at))
            )

        res = await db.execute(stmt)
        rows = res.scalars().all()
        return [
            PromptHistoryItem(
                id=r.id,
                lesson_id=r.lesson_id,
                prompt_type=r.prompt_type,
                system_prompt=r.system_prompt,
                version=r.version,
                changed_by=r.changed_by,
                change_summary=r.change_summary,
                created_at=r.created_at,
            )
            for r in rows
        ]

    @staticmethod
    async def rollback_prompt(
        db: AsyncSession,
        prompt_type: str,
        history_id: UUID,
        lesson_id: Optional[UUID] = None,
    ) -> PromptConfigResponse:
        default_info = DEFAULT_PROMPTS.get(prompt_type)
        if not default_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"نوع پرامپت '{prompt_type}' نامعتبر است.",
            )

        # Find history record
        h_res = await db.execute(
            select(LessonPromptHistory).where(LessonPromptHistory.id == history_id)
        )
        hist = h_res.scalar_one_or_none()
        if not hist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="نسخه مورد نظر در سوابق پرامپت یافت نشد.",
            )

        # Update prompt with hist.system_prompt
        update_payload = PromptConfigUpdate(
            content=hist.system_prompt,
            change_summary=f"بازگردانی به نسخه {hist.version}",
            changed_by="admin",
        )
        return await PromptService.update_prompt(
            db=db,
            prompt_type=prompt_type,
            payload=update_payload,
            lesson_id=lesson_id,
        )

    @staticmethod
    async def reset_prompt(
        db: AsyncSession, prompt_type: str, lesson_id: Optional[UUID] = None
    ) -> PromptConfigResponse:
        default_info = DEFAULT_PROMPTS.get(prompt_type)
        if not default_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"نوع پرامپت '{prompt_type}' نامعتبر است.",
            )

        if lesson_id:
            stmt = select(LessonPromptConfig).where(
                and_(
                    LessonPromptConfig.lesson_id == lesson_id,
                    LessonPromptConfig.prompt_type == prompt_type,
                )
            )
        else:
            stmt = select(LessonPromptConfig).where(
                and_(
                    LessonPromptConfig.lesson_id.is_(None),
                    LessonPromptConfig.prompt_type == prompt_type,
                )
            )

        res = await db.execute(stmt)
        cfg = res.scalar_one_or_none()
        if cfg:
            await db.delete(cfg)
            await db.commit()

        # Record reset in history
        history_entry = LessonPromptHistory(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            system_prompt=default_info["content"],
            version=1,
            changed_by="admin",
            change_summary="بازنشانی به پیش‌فرض سامانه",
        )
        db.add(history_entry)
        await db.commit()

        # Check if a global fallback exists if lesson_id was provided
        content = default_info["content"]
        is_overridden = False
        if lesson_id:
            g_res = await db.execute(
                select(LessonPromptConfig).where(
                    and_(
                        LessonPromptConfig.lesson_id.is_(None),
                        LessonPromptConfig.prompt_type == prompt_type,
                    )
                )
            )
            g_cfg = g_res.scalar_one_or_none()
            if g_cfg:
                content = g_cfg.system_prompt

        params = [
            PromptParameter(**p) for p in default_info.get("parameters", [])
        ]

        return PromptConfigResponse(
            id=None,
            prompt_type=prompt_type,
            name=default_info["name"],
            name_fa=default_info["nameFa"],
            category=default_info["category"],
            source_file=default_info.get("source_file"),
            description=default_info["description"],
            description_fa=default_info["descriptionFa"],
            parameters=params,
            content=content,
            default_content=default_info["content"],
            is_overridden=is_overridden,
            version=1,
            tone_and_style=None,
            custom_rules=[],
            model_override=None,
            is_active=True,
            updated_at=None,
            lesson_id=lesson_id,
        )

    @classmethod
    async def resolve_prompt(
        cls,
        db: AsyncSession,
        prompt_type: str,
        lesson_id: Optional[UUID] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Fast hierarchical prompt resolver for runtime LLM execution.
        Order of resolution:
        1. Lesson-specific custom prompt (if lesson_id provided and active)
        2. Global system override prompt (if active)
        3. Built-in hardcoded default prompt
        """
        raw_prompt = None

        if lesson_id:
            try:
                res = await db.execute(
                    select(LessonPromptConfig.system_prompt).where(
                        and_(
                            LessonPromptConfig.lesson_id == lesson_id,
                            LessonPromptConfig.prompt_type == prompt_type,
                            LessonPromptConfig.is_active.is_(True),
                        )
                    )
                )
                raw_prompt = res.scalar_one_or_none()
            except Exception as e:
                logger.warning(f"Error resolving lesson prompt config: {e}")

        if not raw_prompt:
            try:
                g_res = await db.execute(
                    select(LessonPromptConfig.system_prompt).where(
                        and_(
                            LessonPromptConfig.lesson_id.is_(None),
                            LessonPromptConfig.prompt_type == prompt_type,
                            LessonPromptConfig.is_active.is_(True),
                        )
                    )
                )
                raw_prompt = g_res.scalar_one_or_none()
            except Exception as e:
                logger.warning(f"Error resolving global prompt config: {e}")

        if not raw_prompt:
            default_info = DEFAULT_PROMPTS.get(prompt_type)
            raw_prompt = default_info["content"] if default_info else ""

        if not variables:
            return raw_prompt

        # Safe interpolation without throwing on missing keys
        resolved = raw_prompt
        for key, val in variables.items():
            placeholder = f"{{{key}}}"
            if placeholder in resolved:
                resolved = resolved.replace(placeholder, str(val or ""))

        return resolved
