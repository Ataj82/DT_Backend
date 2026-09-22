import os
import uuid
import json
import secrets
from datetime import datetime, timezone
from typing import Optional, List
from collections import defaultdict

from fastapi import HTTPException, UploadFile, status ,WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.chat.models import (
    Chat,
    ChatMember,
    ChatMemberPermission,
    ChatUserState,
    Message,
    MessageAttachment,
    MessageReaction,
    MessageRead,
    MessageDeletion,
    PinnedMessage,
    ChatInviteLink,
    ChatJoinRequest,
    ChatFolder,
    ChatFolderItem,
)
from app.features.chat.repository import ChatRepository
from app.features.users.repository import UserRepository
from app.core.redis import get_redis


CHAT_TYPES = {
    "PRIVATE",
    "GROUP",
    "SUPERGROUP",
    "CHANNEL",
    "BOT_SESSION",
    "SAVED_MESSAGES",
}

MEMBER_ROLES = {
    "OWNER",
    "ADMIN",
    "MEMBER",
    "BOT",
    "RESTRICTED",
    "LEFT",
    "BANNED",
}

MESSAGE_CONTENT_TYPES = {
    "TEXT",
    "IMAGE",
    "VIDEO",
    "AUDIO",
    "VOICE",
    "FILE",
    "STICKER",
    "GIF",
    "LOCATION",
    "CONTACT",
    "POLL",
    "QUIZ",
    "SYSTEM",
    "SERVICE",
}

ATTACHMENT_TYPES = {
    "IMAGE",
    "VIDEO",
    "AUDIO",
    "VOICE",
    "DOCUMENT",
    "STICKER",
    "THUMBNAIL",
}


from collections import defaultdict
from typing import Optional
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # chat_id -> list of (user_id, websocket)
        self.chat_connections: dict[UUID, list[tuple[UUID, WebSocket]]] = defaultdict(list)

        # (chat_id, user_id) -> number of active connections
        self.user_connection_counts: dict[tuple[UUID, UUID], int] = defaultdict(int)

        self.global_connections: dict[uuid.UUID, list[WebSocket]] = defaultdict(list)  # user_id -> websockets

    async def connect(
        self,
        websocket: WebSocket,
        chat_id: UUID,
        user_id: UUID,
    ) -> bool:
        await websocket.accept()

        self.chat_connections[chat_id].append((user_id, websocket))

        key = (chat_id, user_id)
        was_offline = self.user_connection_counts.get(key, 0) == 0
        self.user_connection_counts[key] += 1

        return was_offline

    def disconnect(
        self,
        chat_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ) -> bool:
        if chat_id in self.chat_connections:
            self.chat_connections[chat_id] = [
                (uid, ws)
                for uid, ws in self.chat_connections[chat_id]
                if ws != websocket
            ]

            if not self.chat_connections[chat_id]:
                del self.chat_connections[chat_id]

        key = (chat_id, user_id)
        current_count = self.user_connection_counts.get(key, 0)

        if current_count <= 0:
            return False

        if current_count == 1:
            self.user_connection_counts.pop(key, None)
            return True

        self.user_connection_counts[key] = current_count - 1
        return False

    async def send_to_user_in_chat(
        self,
        chat_id: UUID,
        user_id: UUID,
        message: str,
    ) -> None:
        if chat_id not in self.chat_connections:
            return

        dead_connections: list[WebSocket] = []

        for uid, websocket in list(self.chat_connections[chat_id]):
            if uid != user_id:
                continue
            try:
                await websocket.send_text(message)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(chat_id=chat_id, user_id=user_id, websocket=websocket)

    async def broadcast_to_chat(
        self,
        chat_id: UUID,
        message: str,
        exclude_user: Optional[UUID] = None,
    ) -> None:
        if chat_id not in self.chat_connections:
            return

        dead_connections: list[tuple[UUID, WebSocket]] = []

        for uid, websocket in list(self.chat_connections[chat_id]):
            if exclude_user and (uid == exclude_user or str(uid) == str(exclude_user)):
                continue

            try:
                await websocket.send_text(message)
            except Exception:
                dead_connections.append((uid, websocket))

        for uid, websocket in dead_connections:
            self.disconnect(chat_id=chat_id, user_id=uid, websocket=websocket)

    def get_user_connection_count(
        self,
        chat_id: UUID,
        user_id: UUID,
    ) -> int:
        return self.user_connection_counts.get((chat_id, user_id), 0)

    def is_user_online(
        self,
        chat_id: UUID,
        user_id: UUID,
    ) -> bool:
        return self.get_user_connection_count(chat_id, user_id) > 0

    def is_user_online_globally(self, user_id: uuid.UUID) -> bool:
        if len(self.global_connections.get(user_id, [])) > 0:
            return True
        for conns in self.chat_connections.values():
            for uid, _ in conns:
                if uid == user_id:
                    return True
        return False
    
    
    async def connect_global(self, websocket: WebSocket, user_id: uuid.UUID):
        await websocket.accept()
        self.global_connections[user_id].append(websocket)

    def disconnect_global(self, user_id: uuid.UUID, websocket: WebSocket):
        if user_id in self.global_connections:
            self.global_connections[user_id] = [
                ws for ws in self.global_connections[user_id] if ws != websocket
            ]
            if not self.global_connections[user_id]:
                del self.global_connections[user_id]

    async def send_to_user_global(self, user_id: uuid.UUID, message: str):
        """Send message to all global websocket connections of a user"""
        print(f"User {user_id} ")

        if user_id not in self.global_connections:
            return

        dead_connections: list[WebSocket] = []
        for ws in list(self.global_connections[user_id]):
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect_global(user_id, ws)


manager = ConnectionManager()


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ChatRepository(db)
        self.user_repo = UserRepository(db)

    async def _commit(self):
        await self.repo.commit()

    async def _rollback(self):
        await self.repo.rollback()

    async def _ensure_chat(self, chat_id: uuid.UUID) -> Chat:
        chat = await self.repo.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")
        return chat

    async def _ensure_message(self, chat_id: uuid.UUID, message_id: uuid.UUID) -> Message:
        msg = await self.repo.get_message(chat_id, message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found.")
        return msg

    async def _ensure_state(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> ChatUserState:
        state = await self.repo.get_chat_user_state(chat_id, user_id)
        if state:
            return state

        member = await self.repo.get_member(chat_id, user_id)
        state = ChatUserState(
            chat_id=chat_id,
            user_id=user_id,
            chat_member_id=member.chat_member_id if member else None,
            unread_count=0,
        )
        await self.repo.create_chat_user_state(state)
        return state

    # ============================================================
    # Chats
    # ============================================================

    async def get_my_chats(
        self,
        user_id: uuid.UUID,
        limit: int,
        cursor: Optional[str] = None,
        archived: Optional[bool] = False,
        folder_id: Optional[uuid.UUID] = None,
        q: Optional[str] = None,
    ):
        folder_chat_ids = None
        if folder_id:
            folder_chat_ids = await self.repo.list_folder_chat_ids(folder_id, user_id)

        rows = await self.repo.list_user_chats(
            user_id=user_id,
            limit=limit,
            archived=archived,
            q=q,
            folder_chat_ids=folder_chat_ids,
        )

        items = []
        redis = get_redis()
        for chat, state in rows:
            last_message = None
            if chat.last_message_id:
                last_message = await self.repo.get_message(chat.chat_id, chat.last_message_id)

            display_title = chat.title
            display_username = chat.username
            display_avatar_url = getattr(chat, 'avatar_url', None)

            is_user_online = False
            last_seen_at_val = None

            # Enrich metadata for private chats and saved messages
            if chat.chat_type == "PRIVATE" or chat.chat_type == "SAVED_MESSAGES":
                members = await self.repo.list_members(chat.chat_id, role=None, limit=2, offset=0)
                other_member = next((m for m in members if m.user_id != user_id), None)
                if chat.chat_type == "SAVED_MESSAGES":
                    # For saved messages, the other member is the user themselves
                    other_member = next((m for m in members if m.user_id == user_id), None)
                
                if other_member:
                    other_user = await self.user_repo.get_by_id(other_member.user_id)
                    if other_user:
                        full_name = f"{other_user.first_name or ''} {other_user.last_name or ''}".strip()
                        display_title = full_name if full_name else (other_user.username or chat.title or "")
                        display_username = getattr(other_user, 'username', None)

                        is_user_online = manager.is_user_online_globally(other_member.user_id)
                        last_seen_at_val = other_user.last_seen_at

                        can_see_photo = True
                        if other_member.user_id != user_id and redis:
                            try:
                                raw_s = await redis.get(f"user:settings:{other_member.user_id}")
                                if raw_s:
                                    s_data = json.loads(raw_s).get("privacy", {})
                                    if s_data.get("profilePhoto") == "nobody":
                                        can_see_photo = False
                                    if s_data.get("lastSeen") == "nobody":
                                        last_seen_at_val = None
                                        is_user_online = False
                            except Exception:
                                pass

                        if can_see_photo:
                            user_avatar = getattr(other_user, 'profile_url', None) or getattr(other_user, 'avatar_url', None)
                            if user_avatar:
                                display_avatar_url = user_avatar
                        else:
                            display_avatar_url = None

            items.append({
                "chat": chat,
                "state": state,
                "last_message": last_message,
                "unread_count": state.unread_count if state else 0,
                "display_title": display_title,
                "display_username": display_username,
                "display_avatar_url": display_avatar_url,
                "is_online": is_user_online,
                "last_seen_at": last_seen_at_val,
            })
        return items

    async def create_chat(
        self,
        actor_id: uuid.UUID,
        chat_type: str,
        user_ids: List[uuid.UUID],
        title: Optional[str],
        description: Optional[str],
        avatar_url: Optional[str],
        is_public: bool,
        username: Optional[str],
    ):
        try:
            if chat_type not in CHAT_TYPES:
                raise HTTPException(status_code=400, detail="Invalid chat type.")

            user_ids = user_ids or []

            if chat_type == "PRIVATE":
                is_public = False

                # In private chat, username corresponds to the target user
                if username:
                    target_user = await self.user_repo.get_user_by_username(username)

                    if not target_user:
                        raise HTTPException(status_code=404, detail="User not found.")

                    if target_user.user_id == actor_id:
                        raise HTTPException(status_code=400, detail="You cannot create private chat with yourself.")

                    user_ids.append(target_user.user_id)

                chat_username = None

            else:
                chat_username = username

                if chat_username:
                    existing = await self.repo.get_chat_by_username(chat_username)
                    if existing:
                        raise HTTPException(status_code=409, detail="Username already exists.")

            unique_user_ids = list(set(user_ids + [actor_id]))

            if chat_type == "PRIVATE":
                if len(unique_user_ids) != 2:
                    raise HTTPException(
                        status_code=400,
                        detail="Private chat must contain exactly 2 users."
                    )
                
                # Check if a private chat already exists
                existing_chat = await self.repo.get_private_chat(actor_id, target_user.user_id) if username else await self.repo.get_private_chat(actor_id, [u for u in unique_user_ids if u != actor_id][0])
                if existing_chat:
                    if existing_chat.chat_type == "PRIVATE" or existing_chat.chat_type == "SAVED_MESSAGES":
                        members_list = await self.repo.list_members(existing_chat.chat_id, role=None, limit=2, offset=0)
                        other_member = next((m for m in members_list if m.user_id != actor_id), None)
                        if existing_chat.chat_type == "SAVED_MESSAGES":
                            other_member = next((m for m in members_list if m.user_id == actor_id), None)
                        if other_member:
                            other_user = await self.user_repo.get_by_id(other_member.user_id)
                            if other_user:
                                existing_chat.title = f"{other_user.first_name} {other_user.last_name or ''}".strip()
                                existing_chat.username = other_user.username
                                if hasattr(other_user, 'avatar_url'):
                                    existing_chat.avatar_url = getattr(other_user, 'avatar_url', existing_chat.avatar_url)
                                if hasattr(other_user, 'bio'):
                                    existing_chat.description = getattr(other_user, 'bio', existing_chat.description)
                    return existing_chat

            chat = Chat(
                chat_type=chat_type,
                title=title,
                description=description,
                avatar_url=avatar_url,
                owner_id=actor_id,
                username=chat_username,
                is_public=is_public,
            )

            await self.repo.create_chat(chat)

            for uid in unique_user_ids:
                role = "OWNER" if uid == actor_id else "MEMBER"

                member = ChatMember(
                    chat_id=chat.chat_id,
                    user_id=uid,
                    role=role,
                    invited_by_user_id=actor_id if uid != actor_id else None,
                )
                await self.repo.create_member(member)

                perm = ChatMemberPermission(
                    chat_member_id=member.chat_member_id,
                    can_send_messages=True,
                    can_send_media=True,
                    can_send_polls=True,
                    can_add_web_page_previews=True,
                    can_invite_users=role in ["OWNER", "ADMIN"],
                    can_pin_messages=role in ["OWNER", "ADMIN"],
                    can_delete_messages=role in ["OWNER", "ADMIN"],
                    can_ban_users=role in ["OWNER", "ADMIN"],
                    can_promote_members=role == "OWNER",
                    can_change_info=role in ["OWNER", "ADMIN"],
                    can_manage_video_chats=role in ["OWNER", "ADMIN"],
                )
                await self.repo.create_member_permission(perm)

                state = ChatUserState(
                    chat_id=chat.chat_id,
                    user_id=uid,
                    chat_member_id=member.chat_member_id,
                    unread_count=0,
                )
                await self.repo.create_chat_user_state(state)

            await self._commit()

            created_chat = await self.repo.get_chat_by_id(chat.chat_id)
            if created_chat.chat_type == "PRIVATE" or created_chat.chat_type == "SAVED_MESSAGES":
                members_list = await self.repo.list_members(created_chat.chat_id, role=None, limit=2, offset=0)
                other_member = next((m for m in members_list if m.user_id != actor_id), None)
                if created_chat.chat_type == "SAVED_MESSAGES":
                    other_member = next((m for m in members_list if m.user_id == actor_id), None)
                if other_member:
                    other_user = await self.user_repo.get_by_id(other_member.user_id)
                    if other_user:
                        created_chat.title = f"{other_user.first_name} {other_user.last_name or ''}".strip()
                        created_chat.username = other_user.username
                        if hasattr(other_user, 'avatar_url'):
                            created_chat.avatar_url = getattr(other_user, 'avatar_url', created_chat.avatar_url)
                        if hasattr(other_user, 'bio'):
                            created_chat.description = getattr(other_user, 'bio', created_chat.description)
            return created_chat

        except Exception as e:
            await self._rollback()
            raise

    
    async def get_chat_detail(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        chat = await self._ensure_chat(chat_id)
        if chat.chat_type == "PRIVATE" or chat.chat_type == "SAVED_MESSAGES":
            members = await self.repo.list_members(chat.chat_id, role=None, limit=2, offset=0)
            other_member = next((m for m in members if m.user_id != user_id), None)
            if chat.chat_type == "SAVED_MESSAGES":
                other_member = next((m for m in members if m.user_id == user_id), None)
            if other_member:
                other_user = await self.user_repo.get_by_id(other_member.user_id)
                if other_user:
                    full_name = f"{other_user.first_name or ''} {other_user.last_name or ''}".strip()
                    chat.title = full_name if full_name else (other_user.username or chat.title)
                    chat.username = other_user.username
                    if hasattr(other_user, 'bio') and other_user.bio:
                        chat.description = other_user.bio

                    is_user_online = manager.is_user_online_globally(other_member.user_id)
                    last_seen_at_val = other_user.last_seen_at

                    redis = get_redis()
                    can_see_photo = True
                    if other_member.user_id != user_id and redis:
                        try:
                            raw_s = await redis.get(f"user:settings:{other_member.user_id}")
                            if raw_s:
                                s_data = json.loads(raw_s).get("privacy", {})
                                if s_data.get("profilePhoto") == "nobody":
                                    can_see_photo = False
                                if s_data.get("lastSeen") == "nobody":
                                    last_seen_at_val = None
                                    is_user_online = False
                        except Exception:
                            pass

                    if can_see_photo:
                        user_avatar = getattr(other_user, 'profile_url', None) or getattr(other_user, 'avatar_url', None)
                        if user_avatar:
                            chat.avatar_url = user_avatar
                    else:
                        chat.avatar_url = None

                    setattr(chat, 'other_user_id', other_member.user_id)
                    setattr(chat, 'is_online', is_user_online)
                    setattr(chat, 'other_user_last_seen_at', last_seen_at_val)
        return chat

    async def update_chat(
        self,
        chat_id: uuid.UUID,
        actor_id: uuid.UUID,
        title: Optional[str],
        description: Optional[str],
        avatar_url: Optional[str],
        username: Optional[str],
        is_public: Optional[bool],
        slow_mode_seconds: Optional[int],
        message_auto_delete_seconds: Optional[int],
    ):
        try:
            chat = await self._ensure_chat(chat_id)

            if username and username != chat.username:
                existing = await self.repo.get_chat_by_username(username)
                if existing and existing.chat_id != chat_id:
                    raise HTTPException(status_code=409, detail="Username already exists.")

            updated = await self.repo.update_chat_fields(
                chat,
                title=title,
                description=description,
                avatar_url=avatar_url,
                username=username,
                is_public=is_public,
                slow_mode_seconds=slow_mode_seconds,
                message_auto_delete_seconds=message_auto_delete_seconds,
            )
            await self._commit()
            return updated
        except Exception:
            await self._rollback()
            raise

    async def delete_chat_for_user(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.deleted_at = datetime.now(timezone.utc)
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def hard_delete_chat(self, chat_id: uuid.UUID, actor_id: uuid.UUID):
        try:
            chat = await self._ensure_chat(chat_id)
            await self.repo.delete_chat(chat)
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # User state
    # ============================================================

    async def get_user_chat_state(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        return await self._ensure_state(chat_id, user_id)

    async def set_chat_archived(self, chat_id: uuid.UUID, user_id: uuid.UUID, archived: bool):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.is_archived = archived
            state.archived_at = datetime.now(timezone.utc) if archived else None
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def set_chat_pinned(self, chat_id: uuid.UUID, user_id: uuid.UUID, pinned: bool):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.is_pinned = pinned
            state.pinned_at = datetime.now(timezone.utc) if pinned else None
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def mute_chat(self, chat_id: uuid.UUID, user_id: uuid.UUID, muted_until: Optional[str]):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.is_muted = True
            state.muted_until = datetime.fromisoformat(muted_until) if muted_until else None
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def unmute_chat(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.is_muted = False
            state.muted_until = None
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def update_draft(self, chat_id: uuid.UUID, user_id: uuid.UUID, draft_text: Optional[str]):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.draft_text = draft_text
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def mark_chat_unread(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        try:
            state = await self._ensure_state(chat_id, user_id)
            state.is_marked_unread = True
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # Messages
    # ============================================================

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        before_message_id: Optional[uuid.UUID],
        after_message_id: Optional[uuid.UUID],
        around_message_id: Optional[uuid.UUID],
        include_deleted: bool,
    ):
        return await self.repo.list_messages(
            chat_id=chat_id,
            limit=limit,
            before_message_id=before_message_id,
            after_message_id=after_message_id,
            include_deleted=include_deleted,
        )

    async def send_message(
        self,
        chat_id: uuid.UUID,
        sender_id: uuid.UUID,
        client_message_id: Optional[str],
        content_type: str,
        text_content: Optional[str],
        metadata_json: Optional[dict],
        reply_to_message_id: Optional[uuid.UUID],
        attachment_ids: List[uuid.UUID],
        is_silent: bool,
        scheduled_at: Optional[datetime],
    ):
        try:
            chat = await self._ensure_chat(chat_id)
            member = await self.repo.get_active_member(chat_id, sender_id)

            if not member:
                raise HTTPException(status_code=403, detail="You are not an active member of this chat.")

            if member.permissions and not member.permissions.can_send_messages:
                raise HTTPException(status_code=403, detail="You cannot send messages in this chat.")

            if content_type not in MESSAGE_CONTENT_TYPES:
                raise HTTPException(status_code=400, detail="Invalid content type.")

            if client_message_id:
                existing = await self.repo.get_message_by_client_id(chat_id, sender_id, client_message_id)
                if existing:
                    return await self.repo.get_message(chat_id, existing.message_id)

            if reply_to_message_id:
                await self._ensure_message(chat_id, reply_to_message_id)

            msg = Message(
                chat_id=chat_id,
                sender_id=sender_id,
                client_message_id=client_message_id,
                content_type=content_type,
                text_content=text_content,
                metadata_json=metadata_json,
                reply_to_message_id=reply_to_message_id,
                is_silent=is_silent,
                scheduled_at=scheduled_at,
            )
            await self.repo.create_message(msg)

            await self.repo.attach_files_to_message(msg.message_id, attachment_ids)

            chat.last_message_id = msg.message_id
            chat.updated_at = datetime.now(timezone.utc)

            members = await self.repo.list_members(chat_id=chat_id, role=None, limit=100000, offset=0)
            for m in members:
                state = await self._ensure_state(chat_id, m.user_id)
                if m.user_id != sender_id and m.left_at is None and not m.is_deleted and m.role not in ["LEFT", "BANNED"]:
                    state.unread_count += 1
                    state.is_marked_unread = False

            await self.repo.flush()
            await self._commit()
            return await self.repo.get_message(chat_id, msg.message_id)
        except Exception:
            await self._rollback()
            raise

    async def get_message(self, chat_id: uuid.UUID, message_id: uuid.UUID, user_id: uuid.UUID):
        msg = await self._ensure_message(chat_id, message_id)
        deletion = await self.repo.get_message_deletion(message_id, user_id)
        if deletion:
            raise HTTPException(status_code=404, detail="Message not found.")
        return msg

    async def edit_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        text_content: Optional[str],
        metadata_json: Optional[dict],
    ):
        try:
            msg = await self._ensure_message(chat_id, message_id)

            if msg.sender_id != actor_id:
                raise HTTPException(status_code=403, detail="Only sender can edit the message.")

            if msg.is_deleted:
                raise HTTPException(status_code=400, detail="Message is deleted.")

            if text_content is not None:
                msg.text_content = text_content
            if metadata_json is not None:
                msg.metadata_json = metadata_json

            msg.is_edited = True
            msg.edit_count += 1
            msg.edited_at = datetime.now(timezone.utc)

            await self.repo.flush()
            await self._commit()
            return await self.repo.get_message(chat_id, message_id)
        except Exception:
            await self._rollback()
            raise

    async def delete_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        delete_for_everyone: bool,
    ):
        try:
            msg = await self._ensure_message(chat_id, message_id)
            actor_member = await self.repo.get_active_member(chat_id, actor_id)

            can_delete_everyone = (
                msg.sender_id == actor_id
                or (actor_member and actor_member.role in ["OWNER", "ADMIN"])
                or (
                    actor_member
                    and actor_member.permissions
                    and actor_member.permissions.can_delete_messages
                )
            )

            if delete_for_everyone:
                if not can_delete_everyone:
                    raise HTTPException(status_code=403, detail="You cannot delete this message for everyone.")
                msg.is_deleted = True
                msg.deleted_at = datetime.now(timezone.utc)
            else:
                deletion = await self.repo.get_message_deletion(message_id, actor_id)
                if not deletion:
                    await self.repo.create_message_deletion(
                        MessageDeletion(
                            message_id=message_id,
                            chat_id=chat_id,
                            user_id=actor_id,
                        )
                    )

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def forward_message(
        self,
        source_chat_id: uuid.UUID,
        source_message_id: uuid.UUID,
        target_chat_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            source = await self._ensure_message(source_chat_id, source_message_id)

            forwarded = Message(
                chat_id=target_chat_id,
                sender_id=actor_id,
                content_type=source.content_type,
                text_content=source.text_content,
                metadata_json=source.metadata_json,
                forward_from_chat_id=source_chat_id,
                forward_from_message_id=source_message_id,
                forward_from_user_id=source.sender_id,
            )
            await self.repo.create_message(forwarded)

            target_chat = await self._ensure_chat(target_chat_id)
            target_chat.last_message_id = forwarded.message_id
            target_chat.updated_at = datetime.now(timezone.utc)

            members = await self.repo.list_members(chat_id=target_chat_id, role=None, limit=100000, offset=0)
            for m in members:
                state = await self._ensure_state(target_chat_id, m.user_id)
                if m.user_id != actor_id and m.left_at is None and not m.is_deleted and m.role not in ["LEFT", "BANNED"]:
                    state.unread_count += 1

            await self.repo.flush()
            await self._commit()
            return await self.repo.get_message(target_chat_id, forwarded.message_id)
        except Exception:
            await self._rollback()
            raise

    async def search_messages(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        q: str,
        limit: int,
        offset: int,
    ):
        return await self.repo.search_messages(chat_id, q, limit, offset)

    # ============================================================
    # Reads
    # ============================================================

    async def mark_read(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        message_id: uuid.UUID,
    ):
        try:
            await self._ensure_message(chat_id, message_id)

            state = await self._ensure_state(chat_id, user_id)
            state.last_read_message_id = message_id
            state.last_read_at = datetime.now(timezone.utc)
            state.unread_count = 0
            state.is_marked_unread = False

            existing = await self.repo.get_message_read(message_id, user_id)
            if not existing:
                await self.repo.create_message_read(
                    MessageRead(
                        message_id=message_id,
                        chat_id=chat_id,
                        user_id=user_id,
                    )
                )

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def get_message_reads(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        await self._ensure_message(chat_id, message_id)
        return await self.repo.get_message_reads(chat_id, message_id)

    # ============================================================
    # Attachments
    # ============================================================

    async def upload_attachment(
        self,
        chat_id: uuid.UUID,
        uploader_id: uuid.UUID,
        file: UploadFile,
        attachment_type: str,
    ):
        try:
            await self._ensure_chat(chat_id)

            if attachment_type not in ATTACHMENT_TYPES:
                raise HTTPException(status_code=400, detail="Invalid attachment type.")

            upload_dir = "uploads/chat"
            os.makedirs(upload_dir, exist_ok=True)

            ext = os.path.splitext(file.filename or "")[1]
            filename = f"{uuid.uuid4()}{ext}"
            storage_key = f"{upload_dir}/{filename}"

            content = await file.read()
            with open(storage_key, "wb") as f:
                f.write(content)

            attachment = MessageAttachment(
                message_id=None,
                chat_id=chat_id,
                uploader_id=uploader_id,
                attachment_type=attachment_type,
                file_name=file.filename,
                mime_type=file.content_type,
                file_size=len(content),
                storage_key=storage_key,
                url=f"/{storage_key}",
            )
            await self.repo.create_attachment(attachment)
            await self._commit()
            return attachment
        except Exception:
            await self._rollback()
            raise

    async def get_attachment(
        self,
        chat_id: uuid.UUID,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ):
        await self._ensure_chat(chat_id)
        attachment = await self.repo.get_attachment(attachment_id)
        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found.")
        return attachment

    async def get_attachment_by_storage_key(
        self,
        storage_key: str,
    ) -> Optional[MessageAttachment]:
        return await self.repo.get_attachment_by_storage_key(storage_key)

    # ============================================================
    # Reactions
    # ============================================================

    async def add_reaction(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        reaction: str,
    ):
        try:
            await self._ensure_message(chat_id, message_id)

            existing = await self.repo.get_reaction(message_id, user_id, reaction)
            if existing:
                return existing

            entity = MessageReaction(
                message_id=message_id,
                chat_id=chat_id,
                user_id=user_id,
                reaction=reaction,
            )
            await self.repo.create_reaction(entity)
            await self._commit()
            return entity
        except Exception:
            await self._rollback()
            raise

    async def remove_reaction(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        reaction: str,
    ):
        try:
            entity = await self.repo.get_reaction(message_id, user_id, reaction)
            if entity:
                await self.repo.delete_reaction(entity)
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # Pinned messages
    # ============================================================

    async def get_pinned_messages(self, chat_id: uuid.UUID, user_id: uuid.UUID):
        return await self.repo.list_pinned_messages(chat_id)

    async def pin_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            msg = await self._ensure_message(chat_id, message_id)
            existing = await self.repo.get_pinned_message(chat_id, message_id)
            if existing:
                return

            msg.is_pinned = True
            await self.repo.create_pinned_message(
                PinnedMessage(
                    chat_id=chat_id,
                    message_id=message_id,
                    pinned_by_user_id=actor_id,
                )
            )
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def unpin_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            msg = await self._ensure_message(chat_id, message_id)
            pinned = await self.repo.get_pinned_message(chat_id, message_id)
            if not pinned:
                return

            msg.is_pinned = False
            await self.repo.delete_pinned_message(pinned)
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # Members
    # ============================================================

    async def get_members(
        self,
        chat_id: uuid.UUID,
        q: Optional[str],
        role: Optional[str],
        limit: int,
        offset: int,
    ):
        members = await self.repo.list_members(chat_id=chat_id, role=role, limit=limit, offset=offset)

        if q:
            q_lower = q.lower()
            filtered = []
            for m in members:
                if q_lower in str(m.user_id).lower():
                    filtered.append(m)
            return filtered
        return members

    async def add_members(
        self,
        chat_id: uuid.UUID,
        actor_id: uuid.UUID,
        user_ids: List[uuid.UUID],
    ):
        try:
            added = []

            for uid in user_ids:
                existing = await self.repo.get_member(chat_id, uid)
                if existing:
                    if existing.left_at is not None or existing.is_deleted or existing.role in ["LEFT", "BANNED"]:
                        existing.left_at = None
                        existing.is_deleted = False
                        existing.role = "MEMBER"
                        existing.banned_until = None
                        added.append(existing)
                    continue

                member = ChatMember(
                    chat_id=chat_id,
                    user_id=uid,
                    role="MEMBER",
                    invited_by_user_id=actor_id,
                )
                await self.repo.create_member(member)

                permission = ChatMemberPermission(
                    chat_member_id=member.chat_member_id,
                    can_send_messages=True,
                    can_send_media=True,
                    can_send_polls=True,
                    can_add_web_page_previews=True,
                    can_invite_users=False,
                    can_pin_messages=False,
                    can_delete_messages=False,
                    can_ban_users=False,
                    can_promote_members=False,
                    can_change_info=False,
                    can_manage_video_chats=False,
                )
                await self.repo.create_member_permission(permission)

                state = await self.repo.get_chat_user_state(chat_id, uid)
                if not state:
                    await self.repo.create_chat_user_state(
                        ChatUserState(
                            chat_id=chat_id,
                            user_id=uid,
                            chat_member_id=member.chat_member_id,
                            unread_count=0,
                        )
                    )

                added.append(member)

            await self._commit()
            return added
        except Exception:
            await self._rollback()
            raise

    async def update_member(
        self,
        chat_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor_id: uuid.UUID,
        role: Optional[str],
        custom_title: Optional[str],
        banned_until: Optional[datetime],
    ):
        try:
            member = await self.repo.get_member(chat_id, target_user_id)
            if not member:
                raise HTTPException(status_code=404, detail="Member not found.")

            if role is not None:
                if role not in MEMBER_ROLES:
                    raise HTTPException(status_code=400, detail="Invalid role.")
                member.role = role

            if custom_title is not None:
                member.custom_title = custom_title

            if banned_until is not None:
                member.banned_until = banned_until

            await self.repo.flush()
            await self._commit()
            return member
        except Exception:
            await self._rollback()
            raise

    async def remove_member(
        self,
        chat_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ):
        try:
            member = await self.repo.get_member(chat_id, target_user_id)
            if not member:
                raise HTTPException(status_code=404, detail="Member not found.")

            member.left_at = datetime.now(timezone.utc)
            member.role = "LEFT"
            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def leave_chat(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
    ):
        try:
            member = await self.repo.get_member(chat_id, user_id)
            if not member:
                raise HTTPException(status_code=404, detail="Member not found.")

            if member.role == "OWNER":
                raise HTTPException(status_code=400, detail="Owner cannot leave chat directly.")

            member.left_at = datetime.now(timezone.utc)
            member.role = "LEFT"

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def update_member_permissions(
        self,
        chat_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor_id: uuid.UUID,
        permissions,
    ):
        try:
            member = await self.repo.get_member(chat_id, target_user_id)
            if not member:
                raise HTTPException(status_code=404, detail="Member not found.")

            if not member.permissions:
                raise HTTPException(status_code=404, detail="Permission row not found.")

            for key, value in permissions.model_dump(exclude_unset=True).items():
                setattr(member.permissions, key, value)

            await self.repo.flush()
            await self._commit()
            return member.permissions
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # Invite links / join requests
    # ============================================================

    async def create_invite_link(
        self,
        chat_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: Optional[str],
        expire_at: Optional[datetime],
        member_limit: Optional[int],
        creates_join_request: bool,
    ):
        try:
            entity = ChatInviteLink(
                chat_id=chat_id,
                created_by_user_id=actor_id,
                token=secrets.token_urlsafe(32),
                name=name,
                expire_at=expire_at,
                member_limit=member_limit,
                usage_count=0,
                creates_join_request=creates_join_request,
                is_revoked=False,
            )
            await self.repo.create_invite_link(entity)
            await self._commit()
            return entity
        except Exception:
            await self._rollback()
            raise

    async def get_invite_links(self, chat_id: uuid.UUID):
        return await self.repo.list_invite_links(chat_id)

    async def revoke_invite_link(
        self,
        chat_id: uuid.UUID,
        invite_link_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            entity = await self.repo.get_invite_link(invite_link_id)
            if not entity or entity.chat_id != chat_id:
                raise HTTPException(status_code=404, detail="Invite link not found.")

            entity.is_revoked = True
            entity.revoked_at = datetime.now(timezone.utc)

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def join_by_invite_token(
        self,
        token: str,
        user_id: uuid.UUID,
    ):
        try:
            link = await self.repo.get_invite_link_by_token(token)
            if not link or link.is_revoked:
                raise HTTPException(status_code=404, detail="Invite link not found.")

            if link.expire_at and link.expire_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Invite link expired.")

            if link.member_limit and link.usage_count >= link.member_limit:
                raise HTTPException(status_code=400, detail="Invite link usage limit exceeded.")

            existing_member = await self.repo.get_member(link.chat_id, user_id)
            if existing_member and existing_member.left_at is None and not existing_member.is_deleted and existing_member.role not in ["LEFT", "BANNED"]:
                return

            if link.creates_join_request:
                await self.repo.create_join_request(
                    ChatJoinRequest(
                        chat_id=link.chat_id,
                        user_id=user_id,
                        invite_link_id=link.invite_link_id,
                        status="PENDING",
                    )
                )
            else:
                await self.add_members(link.chat_id, user_id, [user_id])
                link.usage_count += 1

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def get_join_requests(self, chat_id: uuid.UUID):
        return await self.repo.list_join_requests(chat_id)

    async def approve_join_request(
        self,
        chat_id: uuid.UUID,
        join_request_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            req = await self.repo.get_join_request(join_request_id)
            if not req or req.chat_id != chat_id:
                raise HTTPException(status_code=404, detail="Join request not found.")

            req.status = "APPROVED"
            req.reviewed_at = datetime.now(timezone.utc)
            req.reviewed_by_user_id = actor_id

            await self.add_members(chat_id, actor_id, [req.user_id])

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def reject_join_request(
        self,
        chat_id: uuid.UUID,
        join_request_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        try:
            req = await self.repo.get_join_request(join_request_id)
            if not req or req.chat_id != chat_id:
                raise HTTPException(status_code=404, detail="Join request not found.")

            req.status = "REJECTED"
            req.reviewed_at = datetime.now(timezone.utc)
            req.reviewed_by_user_id = actor_id

            await self.repo.flush()
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    # ============================================================
    # Folders
    # ============================================================

    async def get_folders(self, user_id: uuid.UUID):
        return await self.repo.list_folders(user_id)

    async def create_folder(self, user_id: uuid.UUID, title: str, sort_order: int):
        try:
            folder = ChatFolder(
                user_id=user_id,
                title=title,
                sort_order=sort_order,
            )
            await self.repo.create_folder(folder)
            await self._commit()
            return await self.repo.get_folder(folder.folder_id, user_id)
        except Exception:
            await self._rollback()
            raise

    async def update_folder(
        self,
        folder_id: uuid.UUID,
        user_id: uuid.UUID,
        title: Optional[str],
        sort_order: Optional[int],
    ):
        try:
            folder = await self.repo.get_folder(folder_id, user_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found.")

            if title is not None:
                folder.title = title
            if sort_order is not None:
                folder.sort_order = sort_order

            await self.repo.flush()
            await self._commit()
            return await self.repo.get_folder(folder_id, user_id)
        except Exception:
            await self._rollback()
            raise

    async def delete_folder(self, folder_id: uuid.UUID, user_id: uuid.UUID):
        try:
            folder = await self.repo.get_folder(folder_id, user_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found.")

            await self.repo.delete_folder(folder)
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def add_chat_to_folder(
        self,
        folder_id: uuid.UUID,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
    ):
        try:
            folder = await self.repo.get_folder(folder_id, user_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found.")

            item = await self.repo.get_folder_item(folder_id, chat_id)
            if item:
                return item

            item = ChatFolderItem(
                folder_id=folder_id,
                chat_id=chat_id,
            )
            await self.repo.create_folder_item(item)
            await self._commit()
            return item
        except Exception:
            await self._rollback()
            raise

    async def remove_chat_from_folder(
        self,
        folder_id: uuid.UUID,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
    ):
        try:
            item = await self.repo.get_folder_item(folder_id, chat_id)
            if not item:
                return

            folder = await self.repo.get_folder(folder_id, user_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found.")

            await self.repo.delete_folder_item(item)
            await self._commit()
        except Exception:
            await self._rollback()
            raise


    async def get_other_user_last_read_id(self, chat_id: uuid.UUID, my_user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get the last message ID that the OTHER user has read (for tick status)"""
        chat = await self._ensure_chat(chat_id)
        
        if chat.chat_type != "PRIVATE":
            return None  # For groups we can extend later

        # Find the other user
        members = await self.repo.list_members(chat_id, role=None, limit=2, offset=0)
        other_member = next((m for m in members if m.user_id != my_user_id), None)
        
        if not other_member:
            return None

        state = await self.repo.get_chat_user_state(chat_id, other_member.user_id)
        return state.last_read_message_id if state else None