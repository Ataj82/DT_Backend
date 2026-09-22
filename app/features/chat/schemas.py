import uuid
from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# Frontend-compatible Chat History & RAG Schemas
# ============================================================

class ChatMessageItem(BaseModel):
    id: uuid.UUID
    text: str
    sender: str
    time: str
    date: str
    feedback: Optional[str] = None

class ChatHistoryMessageCreate(BaseModel):
    text: str
    sender: Optional[str] = "me"
    answer: Optional[str] = None
    chatType: Optional[str] = "course"
    targetId: Optional[str] = None
    courseName: Optional[str] = None
    language: Optional[str] = "fa"


class MessageFeedbackRequest(BaseModel):
    feedback: Optional[str] = None

# ============================================================
# Chat
# ============================================================

class ChatCreate(BaseModel):
    chat_type: str
    user_ids: List[uuid.UUID] = Field(default_factory=list)
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    is_public: bool = False
    username: Optional[str] = None


class ChatUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    is_public: Optional[bool] = None
    slow_mode_seconds: Optional[int] = Field(default=None, ge=0)
    message_auto_delete_seconds: Optional[int] = Field(default=None, ge=0)


class ChatResponse(BaseModel):
    chat_id: uuid.UUID
    chat_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    username: Optional[str] = None
    is_public: bool
    is_verified: bool
    is_scam: bool
    is_fake: bool
    slow_mode_seconds: int
    message_auto_delete_seconds: Optional[int] = None
    last_message_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    other_user_id: Optional[uuid.UUID] = None
    is_online: Optional[bool] = False
    other_user_last_seen_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChatUserStateResponse(BaseModel):
    state_id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    chat_member_id: Optional[uuid.UUID] = None
    last_read_message_id: Optional[uuid.UUID] = None
    last_read_at: Optional[datetime] = None
    unread_count: int
    is_muted: bool
    muted_until: Optional[datetime] = None
    is_pinned: bool
    pinned_at: Optional[datetime] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    is_marked_unread: bool
    draft_text: Optional[str] = None
    cleared_until_message_id: Optional[uuid.UUID] = None
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChatListItemResponse(BaseModel):
    chat: ChatResponse
    state: Optional[ChatUserStateResponse] = None
    last_message: Optional["MessageResponse"] = None
    unread_count: int = 0
    display_title: Optional[str] = None
    display_username: Optional[str] = None
    display_avatar_url: Optional[str] = None
    is_online: Optional[bool] = False
    last_seen_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Attachments
# ============================================================

class AttachmentResponse(BaseModel):
    attachment_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    uploader_id: Optional[uuid.UUID] = None
    attachment_type: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    storage_key: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[int] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Reactions
# ============================================================

class ReactionCreate(BaseModel):
    reaction: str = Field(..., min_length=1, max_length=32)


class ReactionResponse(BaseModel):
    reaction_id: uuid.UUID
    message_id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    reaction: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Message
# ============================================================

class MessageCreate(BaseModel):
    client_message_id: Optional[str] = None
    content_type: str = "TEXT"
    text_content: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    reply_to_message_id: Optional[uuid.UUID] = None
    attachment_ids: List[uuid.UUID] = Field(default_factory=list)
    is_silent: bool = False
    scheduled_at: Optional[datetime] = None


class MessageUpdate(BaseModel):
    text_content: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class MessageDeleteRequest(BaseModel):
    delete_for_everyone: bool = False


class MessageForwardRequest(BaseModel):
    target_chat_id: uuid.UUID


class MessageResponse(BaseModel):
    message_id: uuid.UUID
    client_message_id: Optional[str] = None
    chat_id: uuid.UUID
    sender_id: Optional[uuid.UUID] = None
    content_type: str
    text_content: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    reply_to_message_id: Optional[uuid.UUID] = None
    forward_from_chat_id: Optional[uuid.UUID] = None
    forward_from_message_id: Optional[uuid.UUID] = None
    forward_from_user_id: Optional[uuid.UUID] = None
    via_bot_id: Optional[uuid.UUID] = None
    views_count: int
    forwards_count: int
    replies_count: int
    is_pinned: bool
    is_silent: bool
    is_edited: bool
    is_deleted: bool
    edit_count: int
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    created_at: datetime
    attachments: List[AttachmentResponse] = Field(default_factory=list)
    reactions: List[ReactionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Members / Permissions
# ============================================================

class MemberAddRequest(BaseModel):
    user_ids: List[uuid.UUID] = Field(..., min_length=1)


class MemberUpdateRequest(BaseModel):
    role: Optional[str] = None
    custom_title: Optional[str] = None
    banned_until: Optional[datetime] = None


class PermissionUpdate(BaseModel):
    can_send_messages: Optional[bool] = None
    can_send_media: Optional[bool] = None
    can_send_polls: Optional[bool] = None
    can_add_web_page_previews: Optional[bool] = None
    can_invite_users: Optional[bool] = None
    can_pin_messages: Optional[bool] = None
    can_delete_messages: Optional[bool] = None
    can_ban_users: Optional[bool] = None
    can_promote_members: Optional[bool] = None
    can_change_info: Optional[bool] = None
    can_manage_video_chats: Optional[bool] = None


class MemberPermissionResponse(BaseModel):
    permission_id: uuid.UUID
    chat_member_id: uuid.UUID
    can_send_messages: bool
    can_send_media: bool
    can_send_polls: bool
    can_add_web_page_previews: bool
    can_invite_users: bool
    can_pin_messages: bool
    can_delete_messages: bool
    can_ban_users: bool
    can_promote_members: bool
    can_change_info: bool
    can_manage_video_chats: bool

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    chat_member_id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    custom_title: Optional[str] = None
    invited_by_user_id: Optional[uuid.UUID] = None
    joined_at: datetime
    left_at: Optional[datetime] = None
    banned_until: Optional[datetime] = None
    is_deleted: bool
    permissions: Optional[MemberPermissionResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Read / Draft / Typing
# ============================================================

class ReadRequest(BaseModel):
    message_id: uuid.UUID


class DraftUpdate(BaseModel):
    draft_text: Optional[str] = None


class TypingRequest(BaseModel):
    is_typing: bool = True


# ============================================================
# Invite Links / Join Requests
# ============================================================

class InviteLinkCreate(BaseModel):
    name: Optional[str] = None
    expire_at: Optional[datetime] = None
    member_limit: Optional[int] = Field(default=None, ge=1)
    creates_join_request: bool = False


class InviteLinkResponse(BaseModel):
    invite_link_id: uuid.UUID
    chat_id: uuid.UUID
    created_by_user_id: Optional[uuid.UUID] = None
    token: str
    name: Optional[str] = None
    expire_at: Optional[datetime] = None
    member_limit: Optional[int] = None
    usage_count: int
    creates_join_request: bool
    is_revoked: bool
    created_at: datetime
    revoked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JoinRequestResponse(BaseModel):
    join_request_id: uuid.UUID
    chat_id: uuid.UUID
    user_id: uuid.UUID
    invite_link_id: Optional[uuid.UUID] = None
    status: str
    requested_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Folders
# ============================================================

class FolderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class FolderUpdate(BaseModel):
    title: Optional[str] = None
    sort_order: Optional[int] = None


class FolderItemResponse(BaseModel):
    folder_item_id: uuid.UUID
    folder_id: uuid.UUID
    chat_id: uuid.UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FolderResponse(BaseModel):
    folder_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    sort_order: int
    created_at: datetime
    items: List[FolderItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


ChatListItemResponse.model_rebuild()


