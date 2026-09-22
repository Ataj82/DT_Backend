from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone as TZ

import sqlalchemy as sa
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.features.users.models import User, UserProfilePhoto, UserContact


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def touch_last_seen(
        self,
        *,
        user_id: uuid.UUID,
    ) -> None:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(last_seen_at=datetime.now(TZ.utc))
        )
        await self.session.execute(stmt)

    async def touch_last_seen_throttled(
        self,
        *,
        user_id: uuid.UUID,
        min_interval_seconds: int = 30,
    ) -> None:
        now = datetime.now(TZ.utc)
        threshold = now - timedelta(seconds=min_interval_seconds)

        stmt = (
            update(User)
            .where(
                User.user_id == user_id,
                (User.last_seen_at.is_(None) | (User.last_seen_at < threshold))
            )
            .values(last_seen_at=now)
        )
        await self.session.execute(stmt)

    async def update_profile(self, user_id: uuid.UUID, **kwargs) -> User | None:
        valid_fields = {k: v for k, v in kwargs.items() if v is not None}
        if valid_fields:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(**valid_fields)
            )
            await self.session.execute(stmt)
            await self.session.commit()
        return await self.get_user_with_photos(user_id)

    async def get_user_with_photos(self, user_id: uuid.UUID) -> User | None:
        from sqlalchemy.orm import selectinload
        stmt = (
            select(User)
            .options(selectinload(User.profile_photos))
            .where(User.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_profile_photos(self, user_id: uuid.UUID) -> list[UserProfilePhoto]:
        from app.features.users.models import UserProfilePhoto
        stmt = (
            select(UserProfilePhoto)
            .where(UserProfilePhoto.user_id == user_id)
            .order_by(UserProfilePhoto.is_primary.desc(), UserProfilePhoto.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_photo_by_id(self, photo_id: uuid.UUID, user_id: uuid.UUID) -> UserProfilePhoto | None:
        from app.features.users.models import UserProfilePhoto
        stmt = select(UserProfilePhoto).where(
            UserProfilePhoto.photo_id == photo_id,
            UserProfilePhoto.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_profile_photo(
        self,
        user_id: uuid.UUID,
        photo_url: str,
        storage_key: str | None = None,
        is_primary: bool = True
    ) -> UserProfilePhoto:
        from app.features.users.models import UserProfilePhoto

        # If primary, reset other photos
        if is_primary:
            await self.session.execute(
                update(UserProfilePhoto)
                .where(UserProfilePhoto.user_id == user_id)
                .values(is_primary=False)
            )

        photo = UserProfilePhoto(
            user_id=user_id,
            photo_url=photo_url,
            storage_key=storage_key,
            is_primary=is_primary
        )
        self.session.add(photo)

        if is_primary:
            await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(profile_url=photo_url)
            )

        await self.session.commit()
        await self.session.refresh(photo)
        return photo

    async def set_primary_photo(self, photo_id: uuid.UUID, user_id: uuid.UUID) -> UserProfilePhoto | None:
        from app.features.users.models import UserProfilePhoto

        photo = await self.get_photo_by_id(photo_id, user_id)
        if not photo:
            return None

        await self.session.execute(
            update(UserProfilePhoto)
            .where(UserProfilePhoto.user_id == user_id)
            .values(is_primary=False)
        )

        photo.is_primary = True
        await self.session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(profile_url=photo.photo_url)
        )

        await self.session.commit()
        await self.session.refresh(photo)
        return photo

    async def delete_profile_photo(self, photo_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        from app.features.users.models import UserProfilePhoto

        photo = await self.get_photo_by_id(photo_id, user_id)
        if not photo:
            return False

        was_primary = photo.is_primary
        await self.session.delete(photo)
        await self.session.flush()

        if was_primary:
            # Reassign primary to the latest remaining photo
            stmt = (
                select(UserProfilePhoto)
                .where(UserProfilePhoto.user_id == user_id)
                .order_by(UserProfilePhoto.created_at.desc())
            )
            result = await self.session.execute(stmt)
            next_photo = result.scalars().first()
            if next_photo:
                next_photo.is_primary = True
                await self.session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(profile_url=next_photo.photo_url)
                )
            else:
                await self.session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(profile_url=None)
                )

        await self.session.commit()
        return True

    # ============================================================
    # Contacts Management
    # ============================================================

    async def get_contacts(self, user_id: uuid.UUID) -> list[UserContact]:
        stmt = (
            select(UserContact)
            .options(joinedload(UserContact.contact_user))
            .where(UserContact.user_id == user_id)
            .order_by(UserContact.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_contact_by_user_id(
        self, user_id: uuid.UUID, contact_user_id: uuid.UUID
    ) -> UserContact | None:
        stmt = (
            select(UserContact)
            .options(joinedload(UserContact.contact_user))
            .where(
                UserContact.user_id == user_id,
                UserContact.contact_user_id == contact_user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_contact_by_id(
        self, contact_id: uuid.UUID
    ) -> UserContact | None:
        stmt = (
            select(UserContact)
            .options(joinedload(UserContact.contact_user))
            .where(UserContact.contact_id == contact_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_contact(
        self,
        user_id: uuid.UUID,
        contact_user_id: uuid.UUID,
        custom_name: str | None = None,
    ) -> UserContact:
        existing = await self.get_contact_by_user_id(user_id, contact_user_id)
        if existing:
            if custom_name is not None:
                existing.custom_name = custom_name
                await self.session.commit()
                await self.session.refresh(existing)
            return existing

        contact = UserContact(
            user_id=user_id,
            contact_user_id=contact_user_id,
            custom_name=custom_name,
        )
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)
        return await self.get_contact_by_id(contact.contact_id) or contact

    async def remove_contact(
        self, user_id: uuid.UUID, contact_target_id: uuid.UUID
    ) -> bool:
        stmt = select(UserContact).where(
            UserContact.user_id == user_id,
            or_(
                UserContact.contact_user_id == contact_target_id,
                UserContact.contact_id == contact_target_id,
            ),
        )
        result = await self.session.execute(stmt)
        contact = result.scalar_one_or_none()
        if not contact:
            return False

        await self.session.delete(contact)
        await self.session.commit()
        return True

    async def update_contact_name(
        self, user_id: uuid.UUID, contact_target_id: uuid.UUID, custom_name: str | None
    ) -> UserContact | None:
        stmt = select(UserContact).where(
            UserContact.user_id == user_id,
            or_(
                UserContact.contact_user_id == contact_target_id,
                UserContact.contact_id == contact_target_id,
            ),
        )
        result = await self.session.execute(stmt)
        contact = result.scalar_one_or_none()
        if not contact:
            return None

        contact.custom_name = custom_name
        await self.session.commit()
        return await self.get_contact_by_id(contact.contact_id)

    async def search_users(
        self, query: str, current_user_id: uuid.UUID, limit: int = 25
    ) -> list[dict]:
        clean_q = query.strip()
        if not clean_q:
            return []

        # Remove leading @ if user searches e.g. @username
        if clean_q.startswith("@"):
            clean_q = clean_q[1:]

        pattern = f"%{clean_q}%"
        stmt = (
            select(User)
            .where(
                User.user_id != current_user_id,
                User.is_deleted.is_(False),
                or_(
                    User.username.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())

        # Check which of these are already in contacts of current_user
        contact_stmt = select(UserContact.contact_user_id).where(
            UserContact.user_id == current_user_id
        )
        c_res = await self.session.execute(contact_stmt)
        contact_ids = set(c_res.scalars().all())

        return [
            {
                "user_id": u.user_id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "profile_url": u.profile_url,
                "bio": u.bio,
                "user_type": u.user_type,
                "last_seen_at": u.last_seen_at,
                "is_contact": u.user_id in contact_ids,
            }
            for u in users
        ]

