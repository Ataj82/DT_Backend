import os
import uuid
import json
from pathlib import Path
from typing import Optional, List

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.features.users.repository import UserRepository
from app.features.users.schemas import (
    UserCreate,
    UserProfileUpdate,
    UserResponse,
    ContactCreate,
    ContactUpdate,
)
from app.core.security import get_password_hash
from app.core.redis import get_redis


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_AVATAR_SIZE = 10 * 1024 * 1024  # 10 MB


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def create_user(self, data: UserCreate):
        existing = await self.repo.get_user_by_username(data.username)
        if existing:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        hashed_password = get_password_hash(data.password)
        return await self.repo.create(
            username=data.username,
            hashed_password=hashed_password,
            first_name=data.first_name,
            last_name=data.last_name,
            bio=data.bio,
            user_type=data.user_type
        )

    async def update_profile(self, user_id: uuid.UUID, data: UserProfileUpdate):
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check unique username if updated
        if data.username and data.username.lower() != user.username.lower():
            existing = await self.repo.get_user_by_username(data.username)
            if existing and existing.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="این نام کاربری قبلاً توسط کاربر دیگری انتخاب شده است."
                )

        update_fields = {}
        if data.first_name is not None:
            update_fields["first_name"] = data.first_name.strip()
        if data.last_name is not None:
            update_fields["last_name"] = data.last_name.strip()
        if data.username is not None:
            update_fields["username"] = data.username.strip()
        if data.bio is not None:
            update_fields["bio"] = data.bio.strip()

        return await self.repo.update_profile(user_id, **update_fields)

    async def upload_profile_photo(self, user_id: uuid.UUID, file: UploadFile):
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="فرمت فایل مجاز نیست. لطفاً عکس با فرمت JPG، PNG یا WebP ارسال کنید."
            )

        content = await file.read()
        if len(content) > MAX_AVATAR_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="حجم عکس نباید بیشتر از ۱۰ مگابایت باشد."
            )

        upload_dir = Path("uploads/avatars")
        upload_dir.mkdir(parents=True, exist_ok=True)

        ext = os.path.splitext(file.filename or "")[1]
        if not ext:
            ext = ".jpg"
        filename = f"{user_id}_{uuid.uuid4().hex[:12]}{ext}"
        storage_path = upload_dir / filename

        with open(storage_path, "wb") as f:
            f.write(content)

        photo_url = f"/bot/v1/uploads/avatars/{filename}"
        storage_key = str(storage_path)

        photo = await self.repo.add_profile_photo(
            user_id=user_id,
            photo_url=photo_url,
            storage_key=storage_key,
            is_primary=True
        )
        return photo

    async def get_user_photos(self, user_id: uuid.UUID):
        return await self.repo.get_profile_photos(user_id)

    async def delete_profile_photo(self, photo_id: uuid.UUID, user_id: uuid.UUID):
        photo = await self.repo.get_photo_by_id(photo_id, user_id)
        if not photo:
            raise HTTPException(status_code=404, detail="عکس نمایه یافت نشد.")

        # Try to delete file from disk
        if photo.storage_key and os.path.exists(photo.storage_key):
            try:
                os.remove(photo.storage_key)
            except Exception:
                pass

        success = await self.repo.delete_profile_photo(photo_id, user_id)
        return {"success": success, "message": "عکس نمایه با موفقیت حذف شد."}

    async def set_primary_photo(self, photo_id: uuid.UUID, user_id: uuid.UUID):
        photo = await self.repo.set_primary_photo(photo_id, user_id)
        if not photo:
            raise HTTPException(status_code=404, detail="عکس نمایه یافت نشد.")
        return photo

    async def _are_contacts(self, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
        if user_a == user_b:
            return True
        try:
            from app.features.users.models import UserContact
            stmt = select(UserContact.contact_id).where(
                (UserContact.user_id == user_a) & (UserContact.contact_user_id == user_b)
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none() is not None:
                return True

            stmt_reciprocal = select(UserContact.contact_id).where(
                (UserContact.user_id == user_b) & (UserContact.contact_user_id == user_a)
            )
            res_reciprocal = await self.db.execute(stmt_reciprocal)
            if res_reciprocal.scalar_one_or_none() is not None:
                return True

            from app.features.chat.models import Chat, ChatMember
            stmt2 = (
                select(ChatMember.chat_id)
                .join(Chat, Chat.chat_id == ChatMember.chat_id)
                .where(
                    Chat.chat_type.in_(["DIRECT", "PRIVATE"]),
                    ChatMember.user_id.in_([user_a, user_b]),
                    ChatMember.is_left.is_(False),
                )
                .group_by(ChatMember.chat_id)
                .having(func.count(ChatMember.user_id) == 2)
            )
            result2 = await self.db.execute(stmt2)
            return result2.scalar_one_or_none() is not None
        except Exception:
            return False

    async def get_user_profile_with_privacy(
        self,
        target_user_id: uuid.UUID,
        viewer_id: uuid.UUID
    ) -> dict:
        user = await self.repo.get_user_with_photos(target_user_id)
        if not user or user.is_deleted:
            raise HTTPException(status_code=404, detail="کاربر یافت نشد.")

        is_owner = target_user_id == viewer_id

        # Convert to dict representation
        profile_data = {
            "user_id": str(user.user_id),
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "bio": user.bio,
            "user_type": user.user_type,
            "profile_url": user.profile_url,
            "last_seen_at": user.last_seen_at,
            "created_at": user.created_at,
            "is_active": user.is_active,
            "profile_photos": [
                {
                    "photo_id": str(p.photo_id),
                    "photo_url": p.photo_url,
                    "is_primary": p.is_primary,
                    "order": p.order,
                    "created_at": p.created_at
                }
                for p in (user.profile_photos or [])
            ]
        }

        if is_owner:
            return profile_data

        # Load privacy settings from Redis
        redis = get_redis()
        privacy = {}
        if redis:
            raw = await redis.get(f"user:settings:{target_user_id}")
            if raw:
                try:
                    privacy = json.loads(raw).get("privacy", {})
                except Exception:
                    privacy = {}

        # 1. Profile photo privacy (everyone | contacts | nobody)
        photo_privacy = privacy.get("profilePhoto", "everyone")
        if photo_privacy == "nobody":
            profile_data["profile_url"] = None
            profile_data["profile_photos"] = []
        elif photo_privacy == "contacts":
            is_contact = await self._are_contacts(target_user_id, viewer_id)
            if not is_contact:
                profile_data["profile_url"] = None
                profile_data["profile_photos"] = []

        # 2. Last seen privacy (everyone | contacts | nobody)
        last_seen_privacy = privacy.get("lastSeen", "contacts")
        if last_seen_privacy == "nobody":
            profile_data["last_seen_at"] = None
        elif last_seen_privacy == "contacts":
            is_contact = await self._are_contacts(target_user_id, viewer_id)
            if not is_contact:
                profile_data["last_seen_at"] = None

        return profile_data

    async def get_user_photos_with_privacy(
        self,
        target_user_id: uuid.UUID,
        viewer_id: uuid.UUID
    ) -> list:
        if target_user_id == viewer_id:
            return await self.repo.get_profile_photos(target_user_id)

        redis = get_redis()
        privacy = {}
        if redis:
            raw = await redis.get(f"user:settings:{target_user_id}")
            if raw:
                try:
                    privacy = json.loads(raw).get("privacy", {})
                except Exception:
                    privacy = {}

        photo_privacy = privacy.get("profilePhoto", "everyone")
        if photo_privacy == "nobody":
            return []
        elif photo_privacy == "contacts":
            is_contact = await self._are_contacts(target_user_id, viewer_id)
            if not is_contact:
                return []

        return await self.repo.get_profile_photos(target_user_id)

    # ============================================================
    # Contacts Management
    # ============================================================

    def _format_contact(self, contact) -> dict:
        u = contact.contact_user
        return {
            "contact_id": contact.contact_id,
            "contact_user_id": contact.contact_user_id,
            "custom_name": contact.custom_name,
            "created_at": contact.created_at,
            "user": {
                "user_id": u.user_id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "profile_url": u.profile_url,
                "bio": u.bio,
                "user_type": u.user_type,
                "last_seen_at": u.last_seen_at,
            } if u else None,
        }

    async def get_user_contacts(self, user_id: uuid.UUID) -> list[dict]:
        contacts = await self.repo.get_contacts(user_id)
        return [self._format_contact(c) for c in contacts if c.contact_user]

    async def add_user_contact(self, user_id: uuid.UUID, payload: ContactCreate) -> dict:
        target_user = None
        if payload.username:
            clean_username = payload.username.strip()
            if clean_username.startswith("@"):
                clean_username = clean_username[1:]
            target_user = await self.repo.get_user_by_username(clean_username)
            if not target_user:
                raise HTTPException(status_code=404, detail="کاربری با این نام کاربری یافت نشد.")
        elif payload.contact_user_id:
            target_user = await self.repo.get_by_id(payload.contact_user_id)
            if not target_user:
                raise HTTPException(status_code=404, detail="کاربر مورد نظر یافت نشد.")
        else:
            raise HTTPException(status_code=400, detail="شناسه کاربری یا نام کاربری الزامی است.")

        if target_user.user_id == user_id:
            raise HTTPException(status_code=400, detail="شما نمی‌توانید خود را به مخاطبین اضافه کنید.")

        contact = await self.repo.add_contact(
            user_id=user_id,
            contact_user_id=target_user.user_id,
            custom_name=payload.custom_name,
        )
        return self._format_contact(contact)

    async def delete_user_contact(self, user_id: uuid.UUID, contact_target_id: uuid.UUID) -> dict:
        success = await self.repo.remove_contact(user_id, contact_target_id)
        if not success:
            raise HTTPException(status_code=404, detail="مخاطب مورد نظر یافت نشد.")
        return {"success": True, "message": "مخاطب با موفقیت حذف شد."}

    async def update_user_contact(
        self, user_id: uuid.UUID, contact_target_id: uuid.UUID, payload: ContactUpdate
    ) -> dict:
        contact = await self.repo.update_contact_name(
            user_id, contact_target_id, payload.custom_name
        )
        if not contact:
            raise HTTPException(status_code=404, detail="مخاطب مورد نظر یافت نشد.")
        return self._format_contact(contact)

    async def search_users(self, current_user_id: uuid.UUID, query: str) -> list[dict]:
        return await self.repo.search_users(query, current_user_id)

