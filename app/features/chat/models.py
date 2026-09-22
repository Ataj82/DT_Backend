import uuid
import sqlalchemy as sa

from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
    Integer,
    BigInteger,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.database import Base


# ============================================================
# Chat
# ============================================================

class Chat(Base):
    __tablename__ = "chats"

    chat_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    # PRIVATE, GROUP, SUPERGROUP, CHANNEL, BOT_SESSION, SAVED_MESSAGES
    chat_type = Column(String(32), nullable=False, index=True)

    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)

    owner_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    username = Column(String(64), nullable=True, unique=True, index=True)

    is_public = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_scam = Column(Boolean, default=False, nullable=False)
    is_fake = Column(Boolean, default=False, nullable=False)

    slow_mode_seconds = Column(Integer, default=0, nullable=False)

    message_auto_delete_seconds = Column(Integer, nullable=True)

    last_message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    members = relationship(
        "ChatMember",
        back_populates="chat",
        cascade="all, delete-orphan",
        foreign_keys="ChatMember.chat_id",
    )

    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        foreign_keys="Message.chat_id",
    )

    last_message = relationship(
        "Message",
        foreign_keys=[last_message_id],
        post_update=True,
    )

    owner = relationship("User", foreign_keys=[owner_id])
    lesson_bot_chat = relationship("LessonBotChat", back_populates="chat", uselist=False)

    __table_args__ = (
        Index("ix_chats_type_updated_at", "chat_type", "updated_at"),
        Index("ix_chats_owner_id", "owner_id"),
    )


# ============================================================
# Chat Members
# ============================================================

class ChatMember(Base):
    __tablename__ = "chat_members"

    chat_member_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # OWNER, ADMIN, MEMBER, BOT, RESTRICTED, LEFT, BANNED
    role = Column(String(32), default="MEMBER", nullable=False)

    custom_title = Column(String(64), nullable=True)

    invited_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    left_at = Column(DateTime(timezone=True), nullable=True)
    banned_until = Column(DateTime(timezone=True), nullable=True)

    is_deleted = Column(Boolean, default=False, nullable=False)

    chat = relationship("Chat", back_populates="members", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])

    permissions = relationship(
        "ChatMemberPermission",
        back_populates="member",
        uselist=False,
        cascade="all, delete-orphan",
    )

    user_state = relationship(
        "ChatUserState",
        back_populates="member",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_member"),
        Index("ix_chat_members_user_id", "user_id"),
        Index("ix_chat_members_chat_id_role", "chat_id", "role"),
    )


class ChatMemberPermission(Base):
    __tablename__ = "chat_member_permissions"

    permission_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_member_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_members.chat_member_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    can_send_messages = Column(Boolean, default=True, nullable=False)
    can_send_media = Column(Boolean, default=True, nullable=False)
    can_send_polls = Column(Boolean, default=True, nullable=False)
    can_add_web_page_previews = Column(Boolean, default=True, nullable=False)

    can_invite_users = Column(Boolean, default=False, nullable=False)
    can_pin_messages = Column(Boolean, default=False, nullable=False)
    can_delete_messages = Column(Boolean, default=False, nullable=False)
    can_ban_users = Column(Boolean, default=False, nullable=False)
    can_promote_members = Column(Boolean, default=False, nullable=False)
    can_change_info = Column(Boolean, default=False, nullable=False)
    can_manage_video_chats = Column(Boolean, default=False, nullable=False)

    member = relationship("ChatMember", back_populates="permissions")


# ============================================================
# Per-user chat state (for unread count, mute, archive, pin chat, draft, etc.)
# ============================================================

class ChatUserState(Base):
    __tablename__ = "chat_user_states"

    state_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    chat_member_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_members.chat_member_id", ondelete="CASCADE"),
        nullable=True,
    )

    last_read_message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    last_read_at = Column(DateTime(timezone=True), nullable=True)

    unread_count = Column(Integer, default=0, nullable=False)

    is_muted = Column(Boolean, default=False, nullable=False)
    muted_until = Column(DateTime(timezone=True), nullable=True)

    is_pinned = Column(Boolean, default=False, nullable=False)
    pinned_at = Column(DateTime(timezone=True), nullable=True)

    is_archived = Column(Boolean, default=False, nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    is_marked_unread = Column(Boolean, default=False, nullable=False)

    draft_text = Column(Text, nullable=True)

    cleared_until_message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    member = relationship("ChatMember", back_populates="user_state", foreign_keys=[chat_member_id])
    chat = relationship("Chat", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])
    last_read_message = relationship("Message", foreign_keys=[last_read_message_id])
    cleared_until_message = relationship("Message", foreign_keys=[cleared_until_message_id])

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_user_state"),
        Index("ix_chat_user_states_user_updated", "user_id", "is_archived", "is_pinned"),
        Index("ix_chat_user_states_chat_user", "chat_id", "user_id"),
    )


# ============================================================
# Message
# ============================================================

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    # Client-side message ID for idempotency
    client_message_id = Column(String(128), nullable=True)

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    sender_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # TEXT, IMAGE, VIDEO, AUDIO, VOICE, FILE, STICKER, GIF, LOCATION,
    # CONTACT, POLL, QUIZ, SYSTEM, SERVICE
    content_type = Column(String(32), default="TEXT", nullable=False)

    text_content = Column(Text, nullable=True)

    # Message metadata for dimensions, duration, location, poll options, etc.
    metadata_json = Column(JSONB, nullable=True)

    reply_to_message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    forward_from_chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    forward_from_message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    forward_from_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    via_bot_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    views_count = Column(Integer, default=0, nullable=False)
    forwards_count = Column(Integer, default=0, nullable=False)
    replies_count = Column(Integer, default=0, nullable=False)

    is_pinned = Column(Boolean, default=False, nullable=False)
    is_silent = Column(Boolean, default=False, nullable=False)
    is_edited = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

    edit_count = Column(Integer, default=0, nullable=False)

    edited_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chat = relationship("Chat", back_populates="messages", foreign_keys=[chat_id])
    sender = relationship("User", foreign_keys=[sender_id])

    reply_to_message = relationship(
        "Message",
        remote_side=[message_id],
        foreign_keys=[reply_to_message_id],
        post_update=True,
    )

    forward_from_chat = relationship("Chat", foreign_keys=[forward_from_chat_id])
    forward_from_message = relationship(
        "Message",
        remote_side=[message_id],
        foreign_keys=[forward_from_message_id],
        post_update=True,
    )
    forward_from_user = relationship("User", foreign_keys=[forward_from_user_id])
    via_bot = relationship("User", foreign_keys=[via_bot_id])

    attachments = relationship(
        "MessageAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    reactions = relationship(
        "MessageReaction",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    reads = relationship(
        "MessageRead",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    deletions = relationship(
        "MessageDeletion",
        back_populates="message",
        cascade="all, delete-orphan",
    )
    quiz_question_id = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_questions.question_id", ondelete="SET NULL"), nullable=True)
    quiz_attempt_id = Column(PG_UUID(as_uuid=True), ForeignKey("quiz_attempts.attempt_id", ondelete="SET NULL"), nullable=True)
    
    quiz_question = relationship("QuizQuestion")
    quiz_attempt = relationship("QuizAttempt")

    __table_args__ = (
        Index("ix_messages_chat_created", "chat_id", "created_at"),
        Index("ix_messages_chat_id_id", "chat_id", "message_id"),
        Index("ix_messages_sender_id", "sender_id"),
        Index("ix_messages_reply_to", "reply_to_message_id"),
        Index("ix_messages_client_message", "chat_id", "sender_id", "client_message_id"),
        UniqueConstraint("chat_id", "sender_id", "client_message_id", name="uq_message_client_id"),
    )


# ============================================================
# Attachments
# ============================================================

class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    attachment_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=True,
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=True,
    )

    uploader_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # IMAGE, VIDEO, AUDIO, VOICE, DOCUMENT, STICKER, THUMBNAIL
    attachment_type = Column(String(32), nullable=False)

    file_name = Column(String(255), nullable=True)
    mime_type = Column(String(128), nullable=True)
    file_size = Column(BigInteger, nullable=True)

    storage_key = Column(Text, nullable=False)
    url = Column(Text, nullable=True)

    thumbnail_url = Column(Text, nullable=True)

    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    metadata_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="attachments")
    chat = relationship("Chat")
    uploader = relationship("User", foreign_keys=[uploader_id])

    __table_args__ = (
        Index("ix_message_attachments_message_id", "message_id"),
        Index("ix_message_attachments_chat_id", "chat_id"),
        Index("ix_message_attachments_storage_key", "storage_key"),
        Index("ix_message_attachments_uploader_id", "uploader_id"),
    )


# ============================================================
# Reactions
# ============================================================

class MessageReaction(Base):
    __tablename__ = "message_reactions"

    reaction_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    reaction = Column(String(32), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="reactions")
    chat = relationship("Chat", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "reaction", name="uq_message_user_reaction"),
        Index("ix_message_reactions_message_id", "message_id"),
        Index("ix_message_reactions_chat_id", "chat_id"),
    )


# ============================================================
# Reads
# ============================================================

class MessageRead(Base):
    __tablename__ = "message_reads"

    read_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    read_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="reads")
    chat = relationship("Chat", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_read_user"),
        Index("ix_message_reads_chat_user", "chat_id", "user_id"),
        Index("ix_message_reads_message_id", "message_id"),
    )


# ============================================================
# Delete for me
# ============================================================

class MessageDeletion(Base):
    __tablename__ = "message_deletions"

    deletion_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    deleted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="deletions")
    chat = relationship("Chat", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_deletion_user"),
        Index("ix_message_deletions_chat_user", "chat_id", "user_id"),
    )


# ============================================================
# Pinned Messages
# ============================================================

class PinnedMessage(Base):
    __tablename__ = "pinned_messages"

    pinned_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    message_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )

    pinned_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    pinned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chat = relationship("Chat", foreign_keys=[chat_id])
    message = relationship("Message", foreign_keys=[message_id])
    pinned_by = relationship("User", foreign_keys=[pinned_by_user_id])

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_pinned_message"),
        Index("ix_pinned_messages_chat_id", "chat_id"),
    )


# ============================================================
# Invite Links
# ============================================================

class ChatInviteLink(Base):
    __tablename__ = "chat_invite_links"

    invite_link_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    created_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    token = Column(String(128), unique=True, nullable=False, index=True)

    name = Column(String(128), nullable=True)

    expire_at = Column(DateTime(timezone=True), nullable=True)
    member_limit = Column(Integer, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)

    creates_join_request = Column(Boolean, default=False, nullable=False)

    is_revoked = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    chat = relationship("Chat", foreign_keys=[chat_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_chat_invite_links_chat_id", "chat_id"),
    )


class ChatJoinRequest(Base):
    __tablename__ = "chat_join_requests"

    join_request_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    invite_link_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_invite_links.invite_link_id", ondelete="SET NULL"),
        nullable=True,
    )

    # PENDING, APPROVED, REJECTED
    status = Column(String(32), default="PENDING", nullable=False)

    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    reviewed_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    chat = relationship("Chat", foreign_keys=[chat_id])
    user = relationship("User", foreign_keys=[user_id])
    invite_link = relationship("ChatInviteLink", foreign_keys=[invite_link_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", "status", name="uq_pending_join_request"),
        Index("ix_chat_join_requests_chat_status", "chat_id", "status"),
    )


# ============================================================
# Folders
# ============================================================

class ChatFolder(Base):
    __tablename__ = "chat_folders"

    folder_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String(128), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    items = relationship(
        "ChatFolderItem",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_chat_folders_user_id", "user_id"),
    )


class ChatFolderItem(Base):
    __tablename__ = "chat_folder_items"

    folder_item_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    folder_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_folders.folder_id", ondelete="CASCADE"),
        nullable=False,
    )

    chat_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.chat_id", ondelete="CASCADE"),
        nullable=False,
    )

    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    folder = relationship("ChatFolder", back_populates="items")
    chat = relationship("Chat", foreign_keys=[chat_id])

    __table_args__ = (
        UniqueConstraint("folder_id", "chat_id", name="uq_folder_chat"),
        Index("ix_chat_folder_items_folder_id", "folder_id"),
    )
