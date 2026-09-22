import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

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


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def flush(self):
        await self.db.flush()

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    # ============================================================
    # Chat
    # ============================================================

    async def create_chat(self, chat: Chat) -> Chat:
        self.db.add(chat)
        await self.db.flush()
        await self.db.refresh(chat)
        return chat

    async def get_chat_by_id(self, chat_id: uuid.UUID) -> Optional[Chat]:
        result = await self.db.execute(
            select(Chat)
            .options(selectinload(Chat.last_message))
            .where(Chat.chat_id == chat_id, Chat.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_chat_by_username(self, username: str) -> Optional[Chat]:
        result = await self.db.execute(
            select(Chat)
            .where(Chat.username == username, Chat.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_private_chat(self, user_id1: uuid.UUID, user_id2: uuid.UUID) -> Optional[Chat]:
        stmt = (
            select(Chat)
            .where(Chat.chat_type == "PRIVATE", Chat.deleted_at.is_(None))
            .where(
                Chat.chat_id.in_(
                    select(ChatMember.chat_id).where(ChatMember.user_id == user_id1)
                )
            )
            .where(
                Chat.chat_id.in_(
                    select(ChatMember.chat_id).where(ChatMember.user_id == user_id2)
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_chats(
        self,
        user_id: uuid.UUID,
        limit: int,
        archived: Optional[bool] = False,
        q: Optional[str] = None,
        folder_chat_ids: Optional[List[uuid.UUID]] = None,
    ):
        stmt = (
            select(Chat, ChatUserState)
            .options(
                selectinload(Chat.members).selectinload(ChatMember.user),
                selectinload(Chat.last_message),
            )
            .join(
                ChatMember,
                and_(
                    ChatMember.chat_id == Chat.chat_id,
                    ChatMember.user_id == user_id,
                    ChatMember.left_at.is_(None),
                    ChatMember.is_deleted.is_(False),
                    ChatMember.role.notin_(["LEFT", "BANNED"]),
                ),
            )
            .outerjoin(
                ChatUserState,
                and_(
                    ChatUserState.chat_id == Chat.chat_id,
                    ChatUserState.user_id == user_id,
                ),
            )
            .where(Chat.deleted_at.is_(None))
        )

        if archived is not None:
            if archived is True:
                stmt = stmt.where(ChatUserState.is_archived.is_(True))
            else:
                stmt = stmt.where(
                    or_(
                        ChatUserState.is_archived.is_(False),
                        ChatUserState.is_archived.is_(None),
                    )
                )

        stmt = stmt.where(
            or_(
                ChatUserState.deleted_at.is_(None),
                ChatUserState.state_id.is_(None),
            )
        )

        if q:
            stmt = stmt.where(
                or_(
                    Chat.title.ilike(f"%{q}%"),
                    Chat.description.ilike(f"%{q}%"),
                    Chat.username.ilike(f"%{q}%"),
                )
            )

        if folder_chat_ids is not None:
            if not folder_chat_ids:
                return []
            stmt = stmt.where(Chat.chat_id.in_(folder_chat_ids))

        stmt = stmt.order_by(
            ChatUserState.is_pinned.desc().nullslast(),
            ChatUserState.pinned_at.desc().nullslast(),
            Chat.updated_at.desc(),
        ).limit(limit)

        result = await self.db.execute(stmt)
        return result.all()

    async def update_chat_fields(self, chat: Chat, **kwargs) -> Chat:
        for key, value in kwargs.items():
            if value is not None:
                setattr(chat, key, value)
        await self.db.flush()
        await self.db.refresh(chat)
        return chat

    async def delete_chat(self, chat: Chat):
        await self.db.delete(chat)
        await self.db.flush()

    # ============================================================
    # Members
    # ============================================================

    async def verify_active_membership(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(ChatMember.chat_member_id).where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
                ChatMember.left_at.is_(None),
                ChatMember.is_deleted.is_(False),
                ChatMember.role.notin_(["LEFT", "BANNED"]),
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_active_member(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatMember]:
        result = await self.db.execute(
            select(ChatMember)
            .options(selectinload(ChatMember.permissions))
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
                ChatMember.left_at.is_(None),
                ChatMember.is_deleted.is_(False),
                ChatMember.role.notin_(["LEFT", "BANNED"]),
            )
        )
        return result.scalar_one_or_none()

    async def get_member(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatMember]:
        result = await self.db.execute(
            select(ChatMember)
            .options(selectinload(ChatMember.permissions))
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_members(
        self,
        chat_id: uuid.UUID,
        role: Optional[str],
        limit: int,
        offset: int,
    ) -> List[ChatMember]:
        stmt = (
            select(ChatMember)
            .options(selectinload(ChatMember.permissions))
            .where(ChatMember.chat_id == chat_id)
            .order_by(ChatMember.joined_at.asc())
            .limit(limit)
            .offset(offset)
        )
        if role:
            stmt = stmt.where(ChatMember.role == role)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create_member(self, member: ChatMember) -> ChatMember:
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def create_member_permission(self, permission: ChatMemberPermission) -> ChatMemberPermission:
        self.db.add(permission)
        await self.db.flush()
        await self.db.refresh(permission)
        return permission

    # ============================================================
    # User state
    # ============================================================

    async def get_chat_user_state(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatUserState]:
        result = await self.db.execute(
            select(ChatUserState).where(
                ChatUserState.chat_id == chat_id,
                ChatUserState.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_chat_user_state(self, state: ChatUserState) -> ChatUserState:
        self.db.add(state)
        await self.db.flush()
        await self.db.refresh(state)
        return state

    # ============================================================
    # Messages
    # ============================================================

    async def get_message(self, chat_id: uuid.UUID, message_id: uuid.UUID) -> Optional[Message]:
        result = await self.db.execute(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(
                Message.chat_id == chat_id,
                Message.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_message_by_id(self, message_id: uuid.UUID) -> Optional[Message]:
        result = await self.db.execute(
            select(Message).where(Message.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_message_by_client_id(
        self,
        chat_id: uuid.UUID,
        sender_id: uuid.UUID,
        client_message_id: str,
    ) -> Optional[Message]:
        result = await self.db.execute(
            select(Message).where(
                Message.chat_id == chat_id,
                Message.sender_id == sender_id,
                Message.client_message_id == client_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_message(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def list_messages(
        self,
        chat_id: uuid.UUID,
        limit: int,
        before_message_id: Optional[uuid.UUID] = None,
        after_message_id: Optional[uuid.UUID] = None,
        include_deleted: bool = False,
    ) -> List[Message]:
        stmt = (
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(Message.chat_id == chat_id)
        )

        if not include_deleted:
            stmt = stmt.where(Message.is_deleted.is_(False))

        if before_message_id:
            before_msg = await self.get_message(chat_id, before_message_id)
            if before_msg:
                stmt = stmt.where(Message.created_at < before_msg.created_at)

        if after_message_id:
            after_msg = await self.get_message(chat_id, after_message_id)
            if after_msg:
                stmt = stmt.where(Message.created_at > after_msg.created_at)

        stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def search_messages(
        self,
        chat_id: uuid.UUID,
        q: str,
        limit: int,
        offset: int,
    ) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(
                Message.chat_id == chat_id,
                Message.is_deleted.is_(False),
                Message.text_content.ilike(f"%{q}%"),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def attach_files_to_message(self, message_id: uuid.UUID, attachment_ids: List[uuid.UUID]):
        if not attachment_ids:
            return

        await self.db.execute(
            update(MessageAttachment)
            .where(MessageAttachment.attachment_id.in_(attachment_ids))
            .values(message_id=message_id)
        )

    # ============================================================
    # Message read
    # ============================================================

    async def get_message_read(self, message_id: uuid.UUID, user_id: uuid.UUID) -> Optional[MessageRead]:
        result = await self.db.execute(
            select(MessageRead).where(
                MessageRead.message_id == message_id,
                MessageRead.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_message_read(self, entity: MessageRead) -> MessageRead:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def get_message_reads(self, chat_id: uuid.UUID, message_id: uuid.UUID) -> List[MessageRead]:
        result = await self.db.execute(
            select(MessageRead).where(
                MessageRead.chat_id == chat_id,
                MessageRead.message_id == message_id,
            )
        )
        return result.scalars().all()

    # ============================================================
    # Message deletions
    # ============================================================

    async def get_message_deletion(self, message_id: uuid.UUID, user_id: uuid.UUID) -> Optional[MessageDeletion]:
        result = await self.db.execute(
            select(MessageDeletion).where(
                MessageDeletion.message_id == message_id,
                MessageDeletion.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_message_deletion(self, entity: MessageDeletion) -> MessageDeletion:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    # ============================================================
    # Attachments
    # ============================================================

    async def create_attachment(self, attachment: MessageAttachment) -> MessageAttachment:
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def get_attachment(self, attachment_id: uuid.UUID) -> Optional[MessageAttachment]:
        result = await self.db.execute(
            select(MessageAttachment).where(
                MessageAttachment.attachment_id == attachment_id
            )
        )
        return result.scalar_one_or_none()

    async def get_attachment_by_storage_key(self, storage_key: str) -> Optional[MessageAttachment]:
        result = await self.db.execute(
            select(MessageAttachment).where(
                MessageAttachment.storage_key == storage_key
            )
        )
        return result.scalar_one_or_none()

    # ============================================================
    # Reactions
    # ============================================================

    async def get_reaction(
        self,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        reaction: str,
    ) -> Optional[MessageReaction]:
        result = await self.db.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.reaction == reaction,
            )
        )
        return result.scalar_one_or_none()

    async def create_reaction(self, entity: MessageReaction) -> MessageReaction:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete_reaction(self, entity: MessageReaction):
        await self.db.delete(entity)
        await self.db.flush()

    # ============================================================
    # Pinned messages
    # ============================================================

    async def get_pinned_message(self, chat_id: uuid.UUID, message_id: uuid.UUID) -> Optional[PinnedMessage]:
        result = await self.db.execute(
            select(PinnedMessage).where(
                PinnedMessage.chat_id == chat_id,
                PinnedMessage.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_pinned_message(self, entity: PinnedMessage) -> PinnedMessage:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete_pinned_message(self, entity: PinnedMessage):
        await self.db.delete(entity)
        await self.db.flush()

    async def list_pinned_messages(self, chat_id: uuid.UUID) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .join(PinnedMessage, PinnedMessage.message_id == Message.message_id)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(PinnedMessage.chat_id == chat_id)
            .order_by(PinnedMessage.pinned_at.desc())
        )
        return result.scalars().all()

    # ============================================================
    # Invite links
    # ============================================================

    async def create_invite_link(self, entity: ChatInviteLink) -> ChatInviteLink:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def list_invite_links(self, chat_id: uuid.UUID) -> List[ChatInviteLink]:
        result = await self.db.execute(
            select(ChatInviteLink)
            .where(ChatInviteLink.chat_id == chat_id)
            .order_by(ChatInviteLink.created_at.desc())
        )
        return result.scalars().all()

    async def get_invite_link(self, invite_link_id: uuid.UUID) -> Optional[ChatInviteLink]:
        result = await self.db.execute(
            select(ChatInviteLink).where(ChatInviteLink.invite_link_id == invite_link_id)
        )
        return result.scalar_one_or_none()

    async def get_invite_link_by_token(self, token: str) -> Optional[ChatInviteLink]:
        result = await self.db.execute(
            select(ChatInviteLink).where(ChatInviteLink.token == token)
        )
        return result.scalar_one_or_none()

    # ============================================================
    # Join requests
    # ============================================================

    async def create_join_request(self, entity: ChatJoinRequest) -> ChatJoinRequest:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def list_join_requests(self, chat_id: uuid.UUID) -> List[ChatJoinRequest]:
        result = await self.db.execute(
            select(ChatJoinRequest)
            .where(ChatJoinRequest.chat_id == chat_id)
            .order_by(ChatJoinRequest.requested_at.desc())
        )
        return result.scalars().all()

    async def get_join_request(self, join_request_id: uuid.UUID) -> Optional[ChatJoinRequest]:
        result = await self.db.execute(
            select(ChatJoinRequest).where(ChatJoinRequest.join_request_id == join_request_id)
        )
        return result.scalar_one_or_none()

    # ============================================================
    # Folders
    # ============================================================

    async def create_folder(self, folder: ChatFolder) -> ChatFolder:
        self.db.add(folder)
        await self.db.flush()
        await self.db.refresh(folder)
        return folder

    async def get_folder(self, folder_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatFolder]:
        result = await self.db.execute(
            select(ChatFolder)
            .options(selectinload(ChatFolder.items))
            .where(
                ChatFolder.folder_id == folder_id,
                ChatFolder.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_folders(self, user_id: uuid.UUID) -> List[ChatFolder]:
        result = await self.db.execute(
            select(ChatFolder)
            .options(selectinload(ChatFolder.items))
            .where(ChatFolder.user_id == user_id)
            .order_by(ChatFolder.sort_order.asc(), ChatFolder.created_at.asc())
        )
        return result.scalars().all()

    async def delete_folder(self, folder: ChatFolder):
        await self.db.delete(folder)
        await self.db.flush()

    async def get_folder_item(self, folder_id: uuid.UUID, chat_id: uuid.UUID) -> Optional[ChatFolderItem]:
        result = await self.db.execute(
            select(ChatFolderItem).where(
                ChatFolderItem.folder_id == folder_id,
                ChatFolderItem.chat_id == chat_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_folder_item(self, item: ChatFolderItem) -> ChatFolderItem:
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_folder_item(self, item: ChatFolderItem):
        await self.db.delete(item)
        await self.db.flush()

    async def list_folder_chat_ids(self, folder_id: uuid.UUID, user_id: uuid.UUID) -> List[uuid.UUID]:
        folder = await self.get_folder(folder_id, user_id)
        if not folder:
            return []
        return [item.chat_id for item in folder.items]

# ============================================================
# Global / Broadcast Helpers
# ============================================================

    async def get_all_active_members(self, chat_id: uuid.UUID) -> List[ChatMember]:
        """
        Get all active members of a chat for global WebSocket broadcasting.
        Used to notify users via their global socket when something happens in a chat.
        """
        result = await self.db.execute(
            select(ChatMember)
            .options(selectinload(ChatMember.user))
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.left_at.is_(None),
                ChatMember.is_deleted.is_(False),
                ChatMember.role.notin_(["LEFT", "BANNED"]),
            )
        )
        return result.scalars().all()