import uuid
from datetime import datetime
from typing import Any
from datetime import timezone as TZ
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.models import UserSession


class UserSessionRepository:
    model = UserSession

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        remember: bool,
        device_name: str | None = None,
        device_type: str | None = None,
        device_brand: str | None = None,
        device_model: str | None = None,
        os_name: str | None = None,
        os_version: str | None = None,
        browser_name: str | None = None,
        browser_version: str | None = None,
        is_mobile: bool = False,
        is_tablet: bool = False,
        is_pc: bool = False,
        is_bot: bool = False,
        ip_address: str | None = None,
        country_code: str | None = None,
        country_name: str | None = None,
        city_name: str | None = None,
        timezone: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        now = datetime.now(TZ.utc)

        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            remember=remember,
            device_name=device_name,
            device_type=device_type,
            device_brand=device_brand,
            device_model=device_model,
            os_name=os_name,
            os_version=os_version,
            browser_name=browser_name,
            browser_version=browser_version,
            is_mobile=is_mobile,
            is_tablet=is_tablet,
            is_pc=is_pc,
            is_bot=is_bot,
            ip_address=ip_address,
            country_code=country_code,
            country_name=country_name,
            city_name=city_name,
            timezone=timezone,
            latitude=latitude,
            longitude=longitude,
            user_agent=user_agent,
            created_at=now,
            last_active_at=now,
        )

        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_by_id(self, user_session_id: uuid.UUID) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.user_session_id == user_session_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_id(
        self,
        *,
        user_session_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> UserSession | None:
        now = datetime.now(TZ.utc)

        stmt = select(UserSession).where(
            UserSession.user_session_id == user_session_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )

        if user_id is not None:
            stmt = stmt.where(UserSession.user_id == user_id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_refresh_token_hash(
        self,
        *,
        refresh_token_hash: str,
    ) -> UserSession | None:
        now = datetime.now(TZ.utc)

        stmt = select(UserSession).where(
            UserSession.refresh_token_hash == refresh_token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        active_only: bool = False,
    ) -> list[UserSession]:
        stmt = select(UserSession).where(UserSession.user_id == user_id)

        if active_only:
            now = datetime.now(TZ.utc)
            stmt = stmt.where(
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )

        stmt = stmt.order_by(
            UserSession.last_active_at.desc(),
            UserSession.created_at.desc(),
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_user(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[UserSession]:
        return await self.get_by_user_id(user_id, active_only=True)

    async def update(
        self,
        session: UserSession,
        **fields: Any,
    ) -> UserSession:
        for key, value in fields.items():
            if hasattr(session, key):
                setattr(session, key, value)

        if hasattr(session, "last_active_at") and "last_active_at" not in fields:
            session.last_active_at = datetime.now(TZ.utc)

        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def update_refresh_token_hash(
        self,
        *,
        user_session_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "refresh_token_hash": refresh_token_hash,
            "last_active_at": datetime.now(TZ.utc),
        }

        if expires_at is not None:
            values["expires_at"] = expires_at

        stmt = (
            update(UserSession)
            .where(UserSession.user_session_id == user_session_id)
            .values(**values)
        )

        await self.db.execute(stmt)

    async def update_last_active(
        self,
        *,
        user_session_id: uuid.UUID,
    ) -> None:
        stmt = (
            update(UserSession)
            .where(UserSession.user_session_id == user_session_id)
            .values(last_active_at=datetime.now(TZ.utc))
        )
        await self.db.execute(stmt)

    async def revoke(
        self,
        session: UserSession | None = None,
        *,
        user_session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        reason: str = "manual",
    ) -> bool:
        now = datetime.now(TZ.utc)

        if session is not None:
            if session.revoked_at is not None:
                return False

            session.revoked_at = now
            if hasattr(session, "revoke_reason"):
                session.revoke_reason = reason

            await self.db.flush()
            return True

        if user_session_id is None:
            return False

        stmt = update(UserSession).where(
            UserSession.user_session_id == user_session_id,
            UserSession.revoked_at.is_(None),
        )

        if user_id is not None:
            stmt = stmt.where(UserSession.user_id == user_id)

        stmt = stmt.values(
            revoked_at=now,
            revoke_reason=reason,
        )

        result = await self.db.execute(stmt)
        return bool(result.rowcount)

    async def revoke_by_id_without_user_check(
        self,
        *,
        user_session_id: uuid.UUID,
        reason: str = "system",
    ) -> bool:
        stmt = (
            update(UserSession)
            .where(
                UserSession.user_session_id == user_session_id,
                UserSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=datetime.now(TZ.utc),
                revoke_reason=reason,
            )
        )

        result = await self.db.execute(stmt)
        return bool(result.rowcount)

    async def revoke_others(
        self,
        *,
        user_id: uuid.UUID,
        current_session_id: uuid.UUID,
        reason: str = "revoke_others",
    ) -> int:
        stmt = (
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.user_session_id != current_session_id,
                UserSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=datetime.now(TZ.utc),
                revoke_reason=reason,
            )
        )

        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def revoke_all_by_user(
        self,
        *,
        user_id: uuid.UUID,
        reason: str = "logout_all",
    ) -> int:
        stmt = (
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=datetime.now(TZ.utc),
                revoke_reason=reason,
            )
        )

        result = await self.db.execute(stmt)
        return result.rowcount or 0
