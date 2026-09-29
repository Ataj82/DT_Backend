import uuid
import json
import logging
from typing import Optional, List, Annotated
from uuid import UUID

logger = logging.getLogger("chat.router")

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
    Path,
    UploadFile,
    File,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.security import decode_token
from app.features.auth.repository import UserSessionRepository
from app.features.users.models import User
from app.features.users.repository import UserRepository
from app.features.chat.services import ChatService, manager
from app.features.chat.repository import ChatRepository
from app.features.chat.schemas import (
    ChatCreate,
    ChatUpdate,
    ChatResponse,
    ChatListItemResponse,
    ChatUserStateResponse,
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageForwardRequest,
    MessageDeleteRequest,
    AttachmentResponse,
    ReactionCreate,
    ReactionResponse,
    MemberAddRequest,
    MemberUpdateRequest,
    MemberResponse,
    PermissionUpdate,
    InviteLinkCreate,
    InviteLinkResponse,
    JoinRequestResponse,
    FolderCreate,
    FolderUpdate,
    FolderResponse,
    TypingRequest,
    ReadRequest,
    DraftUpdate,
)


router = APIRouter()


# ============================================================
# Dependencies
# ============================================================

async def get_chat_service(
    db: AsyncSession = Depends(get_db),
) -> ChatService:
    return ChatService(db)


async def require_chat_member(
    chat_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    repo = ChatRepository(db)
    is_member = await repo.verify_active_membership(chat_id, current_user.user_id)

    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this chat.",
        )

    return current_user


async def require_chat_admin(
    chat_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    repo = ChatRepository(db)
    member = await repo.get_active_member(chat_id, current_user.user_id)

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this chat.",
        )

    if member.role not in ["OWNER", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required.",
        )

    return current_user


async def require_chat_owner(
    chat_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    repo = ChatRepository(db)
    member = await repo.get_active_member(chat_id, current_user.user_id)

    if not member or member.role != "OWNER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required.",
        )

    return current_user


# ============================================================
# Persistent Chat History and RAG Processing Endpoints
# ============================================================

from sqlalchemy import select, delete
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from app.core.config import settings
from app.features.chat.models import Chat, Message
from app.features.lessons.models import Lesson, LessonBotChat, LessonMember
from app.features.chat.schemas import (
    ChatMessageItem,
    ChatHistoryMessageCreate,
    MessageFeedbackRequest,
    MessageCommentCreate,
    MarkCommentReadRequest,
    BulkMarkCommentReadRequest,
)

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

def get_request_timezone(request: Optional[Request] = None) -> ZoneInfo:
    if request:
        tz_hdr = request.headers.get("x-timezone")
        if tz_hdr:
            try:
                return ZoneInfo(tz_hdr)
            except Exception:
                pass
    return TEHRAN_TZ

STUDENT_NAMESPACE = UUID("20000000-0000-4000-8000-000000000000")

def resolve_target_uuid(chat_type: str, target_id_str: str) -> UUID:
    if str(target_id_str).lower() in ("os", "operating-systems"):
        return UUID("c0000000-0000-4000-8000-000000000001")
    try:
        return UUID(target_id_str)
    except Exception:
        if str(target_id_str).isdigit():
            val = int(target_id_str)
            return UUID(f"20000000-0000-4000-8000-{val:012d}")
        import uuid as _u
        return _u.uuid5(STUDENT_NAMESPACE, f"{chat_type}:{target_id_str}")

async def _resolve_or_create_chat(db: AsyncSession, chat_type: str, target_id_str: str) -> UUID:
    target_uuid = resolve_target_uuid(chat_type, target_id_str)

    stmt = select(Chat).where(Chat.chat_id == target_uuid)
    res = await db.execute(stmt)
    chat = res.scalar_one_or_none()

    if not chat:
        if chat_type == "course":
            stmt_lesson = select(Lesson).where(Lesson.lesson_id == target_uuid)
            res_lesson = await db.execute(stmt_lesson)
            lesson = res_lesson.scalar_one_or_none()
            title = lesson.title if lesson else "Course Chat"
        else:
            stmt_user = select(User).where(User.user_id == target_uuid)
            res_user = await db.execute(stmt_user)
            user = res_user.scalar_one_or_none()
            title = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Student Chat"

        chat = Chat(
            chat_id=target_uuid,
            chat_type="COURSE" if chat_type == "course" else "PRIVATE",
            title=title,
            is_public=False,
        )
        db.add(chat)
        await db.flush()

    return target_uuid


@router.get("/{chat_type}/{target_id}/messages", response_model=List[ChatMessageItem])
async def get_persisted_chat_history(
    chat_type: str,
    target_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    chat_id = await _resolve_or_create_chat(db, chat_type, target_id)
    tz = get_request_timezone(request)

    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    formatted_messages = []
    for msg in messages:
        dt = msg.created_at or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(tz)

        feedback = None
        comments = []
        if msg.metadata_json and isinstance(msg.metadata_json, dict):
            feedback = msg.metadata_json.get("feedback")
            raw_comments = msg.metadata_json.get("comments", [])
            for c in raw_comments:
                if isinstance(c, dict):
                    c_dict = dict(c)
                    c_dict.setdefault("is_read", False)
                    c_dict.setdefault("read_by", [])
                    c_dict.setdefault("read_at", None)
                    c_dict.setdefault("message_id", str(msg.message_id))

                    # Localize comment time and date
                    c_created_str = c_dict.get("created_at")
                    c_dt = None
                    if c_created_str:
                        try:
                            c_dt = datetime.fromisoformat(c_created_str)
                        except Exception:
                            c_dt = None
                    if not c_dt:
                        c_dt = dt
                    if c_dt.tzinfo is None:
                        c_dt = c_dt.replace(tzinfo=timezone.utc)
                    c_local_dt = c_dt.astimezone(tz)
                    c_dict["time"] = c_local_dt.strftime("%H:%M")
                    c_dict["date"] = c_local_dt.strftime("%d %B")
                    c_dict["created_at"] = c_dt.isoformat()
                    comments.append(c_dict)

        sender = "me"
        if msg.metadata_json and isinstance(msg.metadata_json, dict) and "sender" in msg.metadata_json:
            sender = msg.metadata_json["sender"]
        elif msg.sender_id is None:
            sender = "other"

        formatted_messages.append(
            ChatMessageItem(
                id=msg.message_id,
                text=msg.text_content or "",
                sender=sender,
                time=local_dt.strftime("%H:%M"),
                date=local_dt.strftime("%d %B"),
                created_at=dt.isoformat(),
                feedback=feedback,
                comments=comments,
            )
        )

    return formatted_messages


@router.post("/{chat_type}/{target_id}/messages")
async def send_chat_message_with_rag(
    chat_type: str,
    target_id: str,
    payload: ChatHistoryMessageCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    target_uuid = resolve_target_uuid(chat_type, target_id)
    if chat_type == "course":
        stmt_l = select(Lesson).where(Lesson.lesson_id == target_uuid)
        res_l = await db.execute(stmt_l)
        lesson_obj = res_l.scalar_one_or_none()
        if lesson_obj and lesson_obj.is_active is False:
            caller_id = None
            if request:
                auth_h = request.headers.get("Authorization")
                if auth_h and auth_h.startswith("Bearer "):
                    try:
                        p = decode_token(auth_h.split(" ")[1])
                        if p.get("sub"):
                            caller_id = UUID(p.get("sub"))
                    except Exception:
                        pass
            if caller_id:
                stmt_u = select(User).where(User.user_id == caller_id)
                res_u = await db.execute(stmt_u)
                caller = res_u.scalar_one_or_none()
                if caller and caller.user_type == "STUDENT":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="این درس توسط استاد غیرفعال شده است و امکان ارسال پیام وجود ندارد.",
                    )

    chat_id = await _resolve_or_create_chat(db, chat_type, target_id)
    tz = get_request_timezone(request)
    now = datetime.now(timezone.utc)
    user_local_now = now.astimezone(tz)

    # 1. Save user message
    user_msg = Message(
        chat_id=chat_id,
        content_type="TEXT",
        text_content=payload.text,
        created_at=now,
        metadata_json={"sender": "me"},
    )
    db.add(user_msg)
    await db.flush()

    user_msg_item = ChatMessageItem(
        id=user_msg.message_id,
        text=user_msg.text_content,
        sender="me",
        time=user_local_now.strftime("%H:%M"),
        date=user_local_now.strftime("%d %B"),
        created_at=now.isoformat(),
        feedback=None,
    )

    # 2. Use provided answer or invoke RAG Service / LLM Service
    ai_text = payload.answer or ""
    if not ai_text:
        try:
            timeout = settings.RAG_TIMEOUT_SECONDS
            form_data = {
                "query": payload.text,
                "contexts": "",
                "language": payload.language or "fa",
                "courseName": payload.courseName or "سیستم عامل",
                "teacherName": "Teacher",
            }
            logger.info(
                ">>> [RAG/LLM REQUEST] Sending chat question to: %s | Query: \"%s\"",
                settings.RAG_API_URL,
                (payload.text[:100] + "...") if len(payload.text) > 100 else payload.text,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(settings.RAG_API_URL, data=form_data)
                logger.info(
                    "<<< [RAG/LLM RESPONSE] Response from %s | Status: %s",
                    settings.RAG_API_URL,
                    resp.status_code,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    ai_text = (
                        data.get("answer")
                        or data.get("response")
                        or data.get("message")
                        or (data if isinstance(data, str) else "")
                    )
                else:
                    logger.warning(
                        "!!! [RAG/LLM WARNING] Non-200 status %s from %s: %s",
                        resp.status_code,
                        settings.RAG_API_URL,
                        resp.text[:300],
                    )
        except Exception as rag_err:
            logger.error(
                "!!! [RAG/LLM ERROR] Exception communicating with %s: %s",
                settings.RAG_API_URL,
                rag_err,
            )
            ai_text = "مشکلی در ارتباط با سرور به وجود آمد."

    if not ai_text:
        ai_text = "مشکلی در ارتباط با سرور به وجود آمد."


    # 3. Save Assistant Response
    ai_now = datetime.now(timezone.utc)
    ai_local_now = ai_now.astimezone(tz)
    ai_msg = Message(
        chat_id=chat_id,
        content_type="TEXT",
        text_content=ai_text,
        created_at=ai_now,
        metadata_json={"sender": "other"},
    )
    db.add(ai_msg)
    await db.commit()

    ai_msg_item = ChatMessageItem(
        id=ai_msg.message_id,
        text=ai_msg.text_content,
        sender="other",
        time=ai_local_now.strftime("%H:%M"),
        date=ai_local_now.strftime("%d %B"),
        created_at=ai_now.isoformat(),
        feedback=None,
    )

    return {
        "success": True,
        "userMessage": user_msg_item,
        "savedMessage": user_msg_item,
        "aiMessage": ai_msg_item,
    }


@router.post("/messages/{message_id}/feedback")
async def submit_message_feedback(
    message_id: UUID,
    payload: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Message).where(Message.message_id == message_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()

    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    current_meta = dict(msg.metadata_json) if msg.metadata_json and isinstance(msg.metadata_json, dict) else {}
    current_meta["feedback"] = payload.feedback
    msg.metadata_json = current_meta
    await db.commit()

    return {"success": True, "messageId": message_id, "feedback": payload.feedback}


@router.post("/messages/{message_id}/comments")
async def add_message_comment(
    message_id: UUID,
    payload: MessageCommentCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Message).where(Message.message_id == message_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()

    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    # Resolve real teacher name - absolutely no mock data
    raw_teacher_name = (payload.teacher_name or "").strip()
    resolved_teacher_name = ""

    # 1. If payload contains a valid non-placeholder teacher name
    if raw_teacher_name and raw_teacher_name not in ("دکتر محمدی", "استاد", "Teacher", "استاد دکتر محمدی"):
        resolved_teacher_name = raw_teacher_name

    # 2. Check authenticated user token in request
    teacher_id_val = None
    if not resolved_teacher_name and request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ")[1]
            try:
                token_payload = decode_token(raw_token)
                sub = token_payload.get("sub")
                if sub:
                    teacher_id_val = str(sub)
                    res_u = await db.execute(select(User).where(User.user_id == UUID(sub)))
                    u = res_u.scalar_one_or_none()
                    if u:
                        real = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username
                        if real:
                            resolved_teacher_name = real
            except Exception:
                pass

    # 3. If still empty, resolve teacher from course / lesson in database
    if not resolved_teacher_name:
        # Check if chat_id matches a lesson
        res_l = await db.execute(select(Lesson).where(Lesson.lesson_id == msg.chat_id))
        lesson = res_l.scalar_one_or_none()
        if not lesson:
            # Check if chat_id is student user in lesson_members
            res_lm = await db.execute(select(LessonMember).where(LessonMember.user_id == msg.chat_id))
            lm = res_lm.scalar_one_or_none()
            if lm:
                res_l = await db.execute(select(Lesson).where(Lesson.lesson_id == lm.lesson_id))
                lesson = res_l.scalar_one_or_none()
            else:
                # Default OS lesson
                res_l = await db.execute(select(Lesson).where(Lesson.lesson_id == UUID("c0000000-0000-4000-8000-000000000001")))
                lesson = res_l.scalar_one_or_none()
        if lesson and lesson.teacher_id:
            teacher_id_val = str(lesson.teacher_id)
            res_t = await db.execute(select(User).where(User.user_id == lesson.teacher_id))
            t_user = res_t.scalar_one_or_none()
            if t_user:
                resolved_teacher_name = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.username

    if not resolved_teacher_name:
        resolved_teacher_name = raw_teacher_name or "دکتر محمد اله بخش"

    current_meta = dict(msg.metadata_json) if msg.metadata_json and isinstance(msg.metadata_json, dict) else {}
    comments = list(current_meta.get("comments", []))
    tz = get_request_timezone(request)
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(tz)
    new_comment = {
        "id": str(uuid.uuid4()),
        "teacher_name": resolved_teacher_name,
        "teacher_id": teacher_id_val,
        "comment": payload.comment,
        "time": local_now.strftime("%H:%M"),
        "date": local_now.strftime("%d %B"),
        "created_at": now.isoformat(),
        "is_read": False,
        "read_by": [],
        "read_at": None,
        "message_id": str(message_id),
    }
    comments.append(new_comment)
    current_meta["comments"] = comments
    msg.metadata_json = current_meta
    flag_modified(msg, "metadata_json")
    await db.commit()

    return {"success": True, "comment": new_comment, "comments": comments}


@router.delete("/messages/{message_id}/comments/{comment_id}")
async def delete_message_comment(
    message_id: UUID,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Message).where(Message.message_id == message_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()

    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    current_meta = dict(msg.metadata_json) if msg.metadata_json and isinstance(msg.metadata_json, dict) else {}
    comments = [c for c in current_meta.get("comments", []) if str(c.get("id")) != str(comment_id)]
    current_meta["comments"] = comments
    msg.metadata_json = current_meta
    flag_modified(msg, "metadata_json")
    await db.commit()

    return {"success": True, "comments": comments}


@router.post("/messages/{message_id}/comments/{comment_id}/read")
async def mark_message_comment_read(
    message_id: UUID,
    comment_id: str,
    payload: Optional[MarkCommentReadRequest] = None,
    student_id: Optional[str] = Query(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Message).where(Message.message_id == message_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()

    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    reader_id = (payload.student_id if payload else None) or student_id
    if not reader_id and request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ")[1]
            try:
                token_payload = decode_token(raw_token)
                reader_id = token_payload.get("sub")
            except Exception:
                pass

    current_meta = dict(msg.metadata_json) if msg.metadata_json and isinstance(msg.metadata_json, dict) else {}
    comments = list(current_meta.get("comments", []))
    now = datetime.now(timezone.utc)
    updated_comment = None

    for c in comments:
        if str(c.get("id")) == str(comment_id):
            c["is_read"] = True
            c["read_at"] = now.isoformat()
            read_by = list(c.get("read_by", []))
            if reader_id and str(reader_id) not in [str(x) for x in read_by]:
                read_by.append(str(reader_id))
            c["read_by"] = read_by
            updated_comment = c
            break

    current_meta["comments"] = comments
    msg.metadata_json = current_meta
    flag_modified(msg, "metadata_json")
    await db.commit()

    return {"success": True, "comment": updated_comment, "comments": comments}


@router.post("/messages/comments/mark-read")
async def bulk_mark_comments_read(
    payload: BulkMarkCommentReadRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    reader_id = payload.student_id
    if not reader_id and request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ")[1]
            try:
                token_payload = decode_token(raw_token)
                reader_id = token_payload.get("sub")
            except Exception:
                pass

    now = datetime.now(timezone.utc)
    comment_id_set = set(str(cid) for cid in (payload.comment_ids or []))

    if payload.target_id and payload.chat_type:
        target_uuid = resolve_target_uuid(payload.chat_type, payload.target_id)
        stmt = select(Message).where(Message.chat_id == target_uuid)
    else:
        stmt = select(Message).where(Message.metadata_json.isnot(None))

    res = await db.execute(stmt)
    messages = res.scalars().all()
    marked_count = 0

    for msg in messages:
        if not msg.metadata_json or not isinstance(msg.metadata_json, dict):
            continue
        comments = list(msg.metadata_json.get("comments", []))
        modified = False
        for c in comments:
            cid = str(c.get("id"))
            if not comment_id_set or cid in comment_id_set:
                c["is_read"] = True
                c["read_at"] = now.isoformat()
                read_by = list(c.get("read_by", []))
                if reader_id and str(reader_id) not in [str(x) for x in read_by]:
                    read_by.append(str(reader_id))
                c["read_by"] = read_by
                modified = True
                marked_count += 1
        if modified:
            current_meta = dict(msg.metadata_json)
            current_meta["comments"] = comments
            msg.metadata_json = current_meta
            flag_modified(msg, "metadata_json")

    await db.commit()
    return {"success": True, "marked_count": marked_count}


@router.get("/students/{student_id}/unread-comments-summary")
async def get_student_unread_comments_summary(
    student_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    student_uuid = resolve_target_uuid("student", student_id)
    tz = get_request_timezone(request)
    course_stmt = select(Chat.chat_id).where(Chat.chat_type == "COURSE")
    course_res = await db.execute(course_stmt)
    course_ids = list(course_res.scalars().all())
    allowed_chat_ids = [student_uuid] + course_ids

    stmt = (
        select(Message)
        .where(
            Message.chat_id.in_(allowed_chat_ids),
            Message.metadata_json.isnot(None),
        )
        .order_by(Message.created_at.desc())
    )
    res = await db.execute(stmt)
    messages = res.scalars().all()

    unread_comments = []
    seen_comment_ids = set()

    for msg in messages:
        if not msg.metadata_json or not isinstance(msg.metadata_json, dict):
            continue
        comments = msg.metadata_json.get("comments", [])
        for c in comments:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id"))
            if cid in seen_comment_ids:
                continue
            read_by = [str(x) for x in c.get("read_by", [])]
            is_read = bool(c.get("is_read", False))
            if msg.chat_id == student_uuid:
                is_already_read = is_read or (student_id and str(student_id) in read_by)
            else:
                is_already_read = (student_id and str(student_id) in read_by) or is_read
            if not is_already_read:
                seen_comment_ids.add(cid)
                c_created_str = c.get("created_at")
                c_dt = None
                if c_created_str:
                    try:
                        c_dt = datetime.fromisoformat(c_created_str)
                    except Exception:
                        c_dt = None
                if not c_dt:
                    c_dt = msg.created_at or datetime.now(timezone.utc)
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=timezone.utc)
                c_local_dt = c_dt.astimezone(tz)
                unread_comments.append({
                    "comment_id": cid,
                    "id": cid,
                    "message_id": str(msg.message_id),
                    "teacher_name": c.get("teacher_name", "استاد"),
                    "comment": c.get("comment", ""),
                    "created_at": c_dt.isoformat(),
                    "time": c_local_dt.strftime("%H:%M"),
                    "date": c_local_dt.strftime("%d %B"),
                    "chat_id": str(msg.chat_id),
                })

    return {
        "success": True,
        "unread_count": len(unread_comments),
        "unread_comments": unread_comments,
    }




@router.delete("/{chat_type}/{target_id}/history")
async def clear_chat_history(
    chat_type: str,
    target_id: str,
    db: AsyncSession = Depends(get_db),
):
    chat_id = await _resolve_or_create_chat(db, chat_type, target_id)
    stmt = delete(Message).where(Message.chat_id == chat_id)
    await db.execute(stmt)
    await db.commit()

    return {"success": True, "cleared": True}


# ============================================================
# Chat list and chat management
# ============================================================

@router.get(
    "/folders/my",
    response_model=List[FolderResponse],
    summary="Get my folders",
)
async def get_my_folders(
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return await service.get_folders(current_user.user_id)


@router.post(
    "/folders",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create folder",
)
async def create_folder(
    payload: FolderCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return await service.create_folder(
        user_id=current_user.user_id,
        title=payload.title,
        sort_order=payload.sort_order,
    )


@router.patch(
    "/folders/{folder_id}",
    response_model=FolderResponse,
    summary="Update folder",
)
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return await service.update_folder(
        folder_id=folder_id,
        user_id=current_user.user_id,
        title=payload.title,
        sort_order=payload.sort_order,
    )


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete folder",
)
async def delete_folder(
    folder_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    await service.delete_folder(folder_id, current_user.user_id)
    return None


@router.post(
    "/folders/{folder_id}/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add chat to folder",
)
async def add_chat_to_folder(
    folder_id: uuid.UUID,
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    await service.add_chat_to_folder(
        folder_id=folder_id,
        chat_id=chat_id,
        user_id=current_user.user_id,
    )
    return None


@router.delete(
    "/folders/{folder_id}/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove chat from folder",
)
async def remove_chat_from_folder(
    folder_id: uuid.UUID,
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    await service.remove_chat_from_folder(
        folder_id=folder_id,
        chat_id=chat_id,
        user_id=current_user.user_id,
    )
    return None


@router.post(
    "/join/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Join chat by invite token",
)
async def join_by_invite(
    token: str,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    await service.join_by_invite_token(
        token=token,
        user_id=current_user.user_id,
    )
    return None


@router.get(
    "",
    response_model=List[ChatListItemResponse],
    summary="Get current user's chat list",
)
async def get_my_chats(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Optional[str] = Query(None),
    archived: Optional[bool] = Query(False),
    folder_id: Optional[uuid.UUID] = Query(None),
    q: Optional[str] = Query(None),
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return await service.get_my_chats(
        user_id=current_user.user_id,
        limit=limit,
        cursor=cursor,
        archived=archived,
        folder_id=folder_id,
        q=q,
    )


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create chat",
)
async def create_chat(
    payload: ChatCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return await service.create_chat(
        actor_id=current_user.user_id,
        chat_type=payload.chat_type,
        user_ids=payload.user_ids,
        title=payload.title,
        description=payload.description,
        avatar_url=payload.avatar_url,
        is_public=payload.is_public,
        username=payload.username,
    )


@router.get(
    "/{chat_id}",
    response_model=ChatResponse,
    summary="Get chat detail",
)
async def get_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_chat_detail(
        chat_id=chat_id,
        user_id=current_user.user_id,
    )


@router.patch(
    "/{chat_id}",
    response_model=ChatResponse,
    summary="Update chat info",
)
async def update_chat(
    chat_id: uuid.UUID,
    payload: ChatUpdate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    chat = await service.update_chat(
        chat_id=chat_id,
        actor_id=current_user.user_id,
        title=payload.title,
        description=payload.description,
        avatar_url=payload.avatar_url,
        username=payload.username,
        is_public=payload.is_public,
        slow_mode_seconds=payload.slow_mode_seconds,
        message_auto_delete_seconds=payload.message_auto_delete_seconds,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "chat.updated",
            "data": {
                "chat_id": str(chat_id),
            },
        }),
    )

    return chat


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete or hide chat for current user",
)
async def delete_chat_for_me(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.delete_chat_for_user(
        chat_id=chat_id,
        user_id=current_user.user_id,
    )
    return None


@router.delete(
    "/{chat_id}/hard",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard delete chat by owner",
)
async def hard_delete_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_owner),
):
    await service.hard_delete_chat(
        chat_id=chat_id,
        actor_id=current_user.user_id,
    )
    return None


# ============================================================
# Per-user chat state
# ============================================================

@router.get(
    "/{chat_id}/state",
    response_model=ChatUserStateResponse,
    summary="Get current user's state in chat",
)
async def get_chat_state(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_user_chat_state(chat_id, current_user.user_id)


@router.post(
    "/{chat_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.set_chat_archived(chat_id, current_user.user_id, True)
    return None


@router.post(
    "/{chat_id}/unarchive",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unarchive_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.set_chat_archived(chat_id, current_user.user_id, False)
    return None


@router.post(
    "/{chat_id}/pin",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def pin_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.set_chat_pinned(chat_id, current_user.user_id, True)
    return None


@router.post(
    "/{chat_id}/unpin",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unpin_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.set_chat_pinned(chat_id, current_user.user_id, False)
    return None


@router.post(
    "/{chat_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mute_chat(
    chat_id: uuid.UUID,
    muted_until: Optional[str] = Query(None),
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.mute_chat(chat_id, current_user.user_id, muted_until)
    return None


@router.post(
    "/{chat_id}/unmute",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unmute_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.unmute_chat(chat_id, current_user.user_id)
    return None


@router.patch(
    "/{chat_id}/draft",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_draft(
    chat_id: uuid.UUID,
    payload: DraftUpdate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.update_draft(
        chat_id=chat_id,
        user_id=current_user.user_id,
        draft_text=payload.draft_text,
    )
    return None


@router.post(
    "/{chat_id}/mark-unread",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_unread(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.mark_chat_unread(chat_id, current_user.user_id)
    return None


# ============================================================
# Messages
# ============================================================

@router.get(
    "/{chat_id}/messages/search",
    response_model=List[MessageResponse],
    summary="Search messages in chat",
)
async def search_messages(
    chat_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.search_messages(
        chat_id=chat_id,
        user_id=current_user.user_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{chat_id}/messages",
    response_model=List[MessageResponse],
    summary="Get messages with cursor pagination",
)
async def get_messages(
    chat_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_message_id: Optional[uuid.UUID] = Query(None),
    after_message_id: Optional[uuid.UUID] = Query(None),
    around_message_id: Optional[uuid.UUID] = Query(None),
    include_deleted: bool = Query(False),
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_messages(
        chat_id=chat_id,
        user_id=current_user.user_id,
        limit=limit,
        before_message_id=before_message_id,
        after_message_id=after_message_id,
        around_message_id=around_message_id,
        include_deleted=include_deleted,
    )


@router.post(
    "/{chat_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message",
)
async def send_message(
    chat_id: uuid.UUID,
    payload: MessageCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
    db: AsyncSession= Depends(get_db)
):
    stmt_lesson = select(Lesson).where(Lesson.lesson_id == chat_id)
    res_l = await db.execute(stmt_lesson)
    lesson_obj = res_l.scalar_one_or_none()
    if lesson_obj and lesson_obj.is_active is False and current_user.user_type == "STUDENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="این درس توسط استاد غیرفعال شده است و امکان ارسال پیام وجود ندارد.",
        )

    msg = await service.send_message(
        chat_id=chat_id,
        sender_id=current_user.user_id,
        client_message_id=payload.client_message_id,
        content_type=payload.content_type,
        text_content=payload.text_content,
        metadata_json=payload.metadata_json,
        reply_to_message_id=payload.reply_to_message_id,
        attachment_ids=payload.attachment_ids,
        is_silent=payload.is_silent,
        scheduled_at=payload.scheduled_at,
    )

    event = {
        "event": "message.created",
        "data": {
            "chat_id": str(chat_id),
            "message_id": str(msg.message_id),
            "sender_id": str(current_user.user_id),
            "content_type": msg.content_type,
            "text_content": msg.text_content,
            "created_at": msg.created_at.isoformat(),
            "client_message_id": payload.client_message_id,
        },
    }

    await manager.broadcast_to_chat(chat_id, json.dumps(event))
    await broadcast_new_message_to_global(
        chat_id=chat_id,
        message=msg,
        sender_id=current_user.user_id,
        db=db
    )

    return msg


@router.get(
    "/{chat_id}/messages/{message_id}",
    response_model=MessageResponse,
    summary="Get single message",
)
async def get_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=current_user.user_id,
    )


@router.patch(
    "/{chat_id}/messages/{message_id}",
    response_model=MessageResponse,
    summary="Edit message",
)
async def edit_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: MessageUpdate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
    db: AsyncSession = Depends(get_db),
):
    msg = await service.edit_message(
        chat_id=chat_id,
        message_id=message_id,
        actor_id=current_user.user_id,
        text_content=payload.text_content,
        metadata_json=payload.metadata_json,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "message.updated",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "text_content": msg.text_content,
                "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
            },
        }),
    )

    await broadcast_update_message_to_global(
        chat_id=chat_id,
        message_id=str(message_id),
        text_content=msg.text_content,
        edited_at=msg.edited_at.isoformat() if msg.edited_at else None,
        db=db
    )

    return msg


@router.delete(
    "/{chat_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete message",
)
async def delete_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: MessageDeleteRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_message(
        chat_id=chat_id,
        message_id=message_id,
        actor_id=current_user.user_id,
        delete_for_everyone=payload.delete_for_everyone,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "message.deleted",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "delete_for_everyone": payload.delete_for_everyone,
                "actor_id": str(current_user.user_id),
            },
        }),
    )

    await broadcast_delete_message_to_global(
        chat_id=chat_id,
        message_id=str(message_id),
        db=db
    )

    return None


@router.post(
    "/{chat_id}/messages/{message_id}/forward",
    response_model=MessageResponse,
    summary="Forward message",
)
async def forward_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: MessageForwardRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
    db: AsyncSession = Depends(get_db),
):
    forwarded = await service.forward_message(
        source_chat_id=chat_id,
        source_message_id=message_id,
        target_chat_id=payload.target_chat_id,
        actor_id=current_user.user_id,
    )

    await manager.broadcast_to_chat(
        payload.target_chat_id,
        json.dumps({
            "event": "message.created",
            "data": {
                "chat_id": str(payload.target_chat_id),
                "message_id": str(forwarded.message_id),
                "sender_id": str(current_user.user_id),
                "content_type": forwarded.content_type,
                "text_content": forwarded.text_content,
                "created_at": forwarded.created_at.isoformat(),
                "forward_from_message_id": str(message_id),
            },
        }),
    )

    await broadcast_new_message_to_global(
        chat_id=payload.target_chat_id,
        message_id=str(forwarded.message_id),
        sender_id=str(current_user.user_id),
        content_type=forwarded.content_type,
        text_content=forwarded.text_content,
        created_at=forwarded.created_at.isoformat(),
        db=db
    )

    return forwarded


# ============================================================
# Message read
# ============================================================

@router.post(
    "/{chat_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark chat as read until message",
)
async def mark_read(
    chat_id: uuid.UUID,
    payload: ReadRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_read(
        chat_id=chat_id,
        user_id=current_user.user_id,
        message_id=payload.message_id,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "message.read",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(current_user.user_id),
                "message_id": str(payload.message_id),
            },
        }),
        exclude_user=current_user.user_id,
    )

    await broadcast_read_to_global(
        chat_id=chat_id,
        reader_id=current_user.user_id,
        message_id=payload.message_id,
        db=db
    )

    return None


@router.get(
    "/{chat_id}/messages/{message_id}/reads",
    summary="Get message read users",
)
async def get_message_reads(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_message_reads(
        chat_id=chat_id,
        message_id=message_id,
        actor_id=current_user.user_id,
    )


# ============================================================
# Attachments
# ============================================================

@router.post(
    "/{chat_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload attachment for chat",
)
async def upload_attachment(
    chat_id: uuid.UUID,
    file: UploadFile = File(...),
    attachment_type: str = Query(...),
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.upload_attachment(
        chat_id=chat_id,
        uploader_id=current_user.user_id,
        file=file,
        attachment_type=attachment_type,
    )


@router.get(
    "/{chat_id}/attachments/{attachment_id}",
    response_model=AttachmentResponse,
)
async def get_attachment(
    chat_id: uuid.UUID,
    attachment_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_attachment(
        chat_id=chat_id,
        attachment_id=attachment_id,
        user_id=current_user.user_id,
    )


# ============================================================
# Reactions
# ============================================================

@router.post(
    "/{chat_id}/messages/{message_id}/reactions",
    response_model=ReactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_reaction(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ReactionCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    reaction = await service.add_reaction(
        chat_id=chat_id,
        message_id=message_id,
        user_id=current_user.user_id,
        reaction=payload.reaction,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "reaction.added",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "user_id": str(current_user.user_id),
                "reaction": payload.reaction,
            },
        }),
    )

    return reaction


@router.delete(
    "/{chat_id}/messages/{message_id}/reactions",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_reaction(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    reaction: str = Query(...),
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.remove_reaction(
        chat_id=chat_id,
        message_id=message_id,
        user_id=current_user.user_id,
        reaction=reaction,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "reaction.removed",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "user_id": str(current_user.user_id),
                "reaction": reaction,
            },
        }),
    )

    return None


# ============================================================
# Pinned messages
# ============================================================

@router.get(
    "/{chat_id}/pinned-messages",
    response_model=List[MessageResponse],
)
async def get_pinned_messages(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_pinned_messages(chat_id, current_user.user_id)


@router.post(
    "/{chat_id}/messages/{message_id}/pin",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def pin_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.pin_message(
        chat_id=chat_id,
        message_id=message_id,
        actor_id=current_user.user_id,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "message.pinned",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "actor_id": str(current_user.user_id),
            },
        }),
    )

    return None


@router.delete(
    "/{chat_id}/messages/{message_id}/pin",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unpin_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.unpin_message(
        chat_id=chat_id,
        message_id=message_id,
        actor_id=current_user.user_id,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "message.unpinned",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message_id),
                "actor_id": str(current_user.user_id),
            },
        }),
    )

    return None


# ============================================================
# Members
# ============================================================

@router.get(
    "/{chat_id}/members",
    response_model=List[MemberResponse],
)
async def get_members(
    chat_id: uuid.UUID,
    q: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    return await service.get_members(
        chat_id=chat_id,
        q=q,
        role=role,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{chat_id}/members",
    response_model=List[MemberResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_members(
    chat_id: uuid.UUID,
    payload: MemberAddRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    members = await service.add_members(
        chat_id=chat_id,
        actor_id=current_user.user_id,
        user_ids=payload.user_ids,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "members.added",
            "data": {
                "chat_id": str(chat_id),
                "actor_id": str(current_user.user_id),
                "user_ids": [str(x) for x in payload.user_ids],
            },
        }),
    )

    return members


@router.patch(
    "/{chat_id}/members/{user_id}",
    response_model=MemberResponse,
)
async def update_member(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberUpdateRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    member = await service.update_member(
        chat_id=chat_id,
        target_user_id=user_id,
        actor_id=current_user.user_id,
        role=payload.role,
        custom_title=payload.custom_title,
        banned_until=payload.banned_until,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "member.updated",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(user_id),
            },
        }),
    )

    return member


@router.delete(
    "/{chat_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.remove_member(
        chat_id=chat_id,
        actor_id=current_user.user_id,
        target_user_id=user_id,
    )

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "member.removed",
            "data": {
                "chat_id": str(chat_id),
                "actor_id": str(current_user.user_id),
                "user_id": str(user_id),
            },
        }),
    )

    return None


@router.post(
    "/{chat_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def leave_chat(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    await service.leave_chat(chat_id, current_user.user_id)

    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "member.left",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(current_user.user_id),
            },
        }),
    )

    return None


@router.patch(
    "/{chat_id}/members/{user_id}/permissions",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_member_permissions(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: PermissionUpdate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_owner),
):
    await service.update_member_permissions(
        chat_id=chat_id,
        target_user_id=user_id,
        actor_id=current_user.user_id,
        permissions=payload,
    )
    return None


# ============================================================
# Invite links and join requests
# ============================================================

@router.post(
    "/{chat_id}/invite-links",
    response_model=InviteLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite_link(
    chat_id: uuid.UUID,
    payload: InviteLinkCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    return await service.create_invite_link(
        chat_id=chat_id,
        actor_id=current_user.user_id,
        name=payload.name,
        expire_at=payload.expire_at,
        member_limit=payload.member_limit,
        creates_join_request=payload.creates_join_request,
    )


@router.get(
    "/{chat_id}/invite-links",
    response_model=List[InviteLinkResponse],
)
async def get_invite_links(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    return await service.get_invite_links(chat_id)


@router.delete(
    "/{chat_id}/invite-links/{invite_link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invite_link(
    chat_id: uuid.UUID,
    invite_link_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.revoke_invite_link(
        chat_id=chat_id,
        invite_link_id=invite_link_id,
        actor_id=current_user.user_id,
    )
    return None


@router.get(
    "/{chat_id}/join-requests",
    response_model=List[JoinRequestResponse],
)
async def get_join_requests(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    return await service.get_join_requests(chat_id)


@router.post(
    "/{chat_id}/join-requests/{join_request_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def approve_join_request(
    chat_id: uuid.UUID,
    join_request_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.approve_join_request(
        chat_id=chat_id,
        join_request_id=join_request_id,
        actor_id=current_user.user_id,
    )
    return None


@router.post(
    "/{chat_id}/join-requests/{join_request_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_join_request(
    chat_id: uuid.UUID,
    join_request_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_admin),
):
    await service.reject_join_request(
        chat_id=chat_id,
        join_request_id=join_request_id,
        actor_id=current_user.user_id,
    )
    return None


# ============================================================
# Typing
# ============================================================

@router.post(
    "/{chat_id}/typing",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def send_typing(
    chat_id: uuid.UUID,
    payload: TypingRequest,
    current_user: User = Depends(require_chat_member),
    db: AsyncSession = Depends(get_db),
):
    await manager.broadcast_to_chat(
        chat_id,
        json.dumps({
            "event": "typing",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(current_user.user_id),
                "is_typing": payload.is_typing,
            },
        }),
        exclude_user=current_user.user_id,
    )

    await broadcast_typing_to_global(
        chat_id=chat_id,
        user_id=current_user.user_id,
        is_typing=payload.is_typing,
        db=db,
    )

    return None

@router.get(
    "/{chat_id}/other-last-read",
    summary="Get other user's last read message ID (for read ticks)"
)
async def get_other_last_read(
    chat_id: uuid.UUID,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(require_chat_member),
):
    last_read_id = await service.get_other_user_last_read_id(
        chat_id=chat_id,
        my_user_id=current_user.user_id
    )
    return {"otherUserLastReadId": str(last_read_id) if last_read_id else None}

# ============================================================
# Validate & Touch Activity (Global Helper)
# ============================================================

async def validate_and_touch_activity(
        *,
        db: AsyncSession,
        session_repo: UserSessionRepository,
        user_repo: UserRepository,
        session_id: UUID,
        user_id: UUID,
    ) -> bool:
        active_session = await session_repo.get_active_by_id(
            user_session_id=session_id,
            user_id=user_id,
        )
        if not active_session:
            return False
        try:
            await session_repo.update_last_active(user_session_id=session_id)
            await user_repo.touch_last_seen_throttled(
                user_id=user_id,
                min_interval_seconds=30,
            )
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise

# ============================================================
# WebSocket Auth
# ============================================================

async def authenticate_websocket_user(
    token: Optional[str],
    db: AsyncSession,
) -> tuple[Optional[User], Optional[UUID]]:
    if not token:
        return None, None

    try:
        payload = decode_token(token)
    except Exception:
        return None, None

    token_type = payload.get("type")
    user_id = payload.get("sub")
    user_session_id = payload.get("user_session_id")

    if token_type != "access":
        return None, None

    if not user_id or not user_session_id:
        return None, None

    try:
        user_uuid = UUID(str(user_id))
        session_uuid = UUID(str(user_session_id))
    except Exception:
        return None, None

    session_repo = UserSessionRepository(db)
    active_session = await session_repo.get_active_by_id(
        user_session_id=session_uuid,
        user_id=user_uuid,
    )
    if not active_session:
        return None, None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_uuid)
    if not user:
        return None, None

    if hasattr(user, "is_active") and not user.is_active:
        return None, None

    if hasattr(user, "is_deleted") and user.is_deleted:
        return None, None

    await session_repo.update_last_active(user_session_id=session_uuid)

    return user, session_uuid


# ============================================================
# WebSocket
# ============================================================
@router.websocket("/global/ws")
async def global_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    current_user, current_session_id = await authenticate_websocket_user(token=token, db=db)

    if not current_user or not current_session_id:
        await websocket.close(code=1008)
        return

    session_repo = UserSessionRepository(db)
    user_repo = UserRepository(db)

    connected = False

    try:
        is_first = len(manager.global_connections.get(current_user.user_id, [])) == 0
        await manager.connect_global(websocket, current_user.user_id)
        connected = True

        await websocket.send_text(json.dumps({
            "event": "global.connected",
            "data": {"user_id": str(current_user.user_id), "status": "connected"}
        }))

        if is_first:
            await broadcast_presence_for_user_chats(
                user_id=current_user.user_id,
                status="online",
                db=db
            )

        while True:
            raw = await websocket.receive_text()
            try:
                packet = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"event": "error", "data": {"message": "Invalid JSON"}}))
                continue

            event = packet.get("event")
            data = packet.get("data") or {}

            if event == "ping":
                ok = await validate_and_touch_activity(
                    db=db, session_repo=session_repo, user_repo=user_repo,
                    session_id=current_session_id, user_id=current_user.user_id
                )
                if not ok:
                    await websocket.close(code=1008)
                    return
                await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                continue

            if event in ("call.offer", "call.answer", "call.reject", "call.end", "call.ice_candidate"):
                target_chat_id = data.get("chat_id")
                if target_chat_id:
                    try:
                        chat_uuid = uuid.UUID(target_chat_id)
                        full_name = f"{getattr(current_user, 'first_name', '') or ''} {getattr(current_user, 'last_name', '') or ''}".strip()
                        caller_name = full_name or getattr(current_user, "username", "") or "کاربر"
                        caller_avatar = getattr(current_user, "profile_url", None)
                        call_payload = {
                            "event": event,
                            "data": {
                                "chat_id": str(target_chat_id),
                                "caller_id": str(current_user.user_id),
                                "caller_name": caller_name,
                                "caller_avatar_url": caller_avatar,
                                **data,
                            },
                        }
                        call_json = json.dumps(call_payload)
                        await manager.broadcast_to_chat(
                            chat_uuid, call_json, exclude_user=current_user.user_id
                        )
                        repo = ChatRepository(db)
                        members = await repo.get_all_active_members(chat_uuid)
                        for member in members:
                            if member.user_id != current_user.user_id:
                                await manager.send_to_user_global(member.user_id, call_json)
                    except Exception as call_err:
                        print(f"[Global WS Call Error] {call_err}")
                continue

    except WebSocketDisconnect:
        pass
    finally:
        if connected:
            manager.disconnect_global(current_user.user_id, websocket)
            if not manager.is_user_online_globally(current_user.user_id):
                try:
                    await user_repo.touch_last_seen(user_id=current_user.user_id)
                    await db.commit()
                except Exception:
                    await db.rollback()

                await broadcast_presence_for_user_chats(
                    user_id=current_user.user_id,
                    status="offline",
                    db=db
                )



@router.websocket("/{chat_id}/ws")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: uuid.UUID,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = ChatRepository(db)
    user_repo = UserRepository(db)



    current_user, current_session_id = await authenticate_websocket_user(
        token=token, db=db
    )

    if not current_user or not current_session_id:
        await websocket.close(code=1008)
        return

    is_member = await repo.verify_active_membership(
        chat_id=chat_id, user_id=current_user.user_id
    )
    if not is_member:
        await websocket.close(code=1008)
        return

    service = ChatService(db)
    session_repo = UserSessionRepository(db)

    connected = False

    try:
        first_connection = await manager.connect(
            websocket, chat_id, current_user.user_id
        )
        connected = True

        # Send initial online users in this chat
        members = await repo.get_all_active_members(chat_id)
        online_members = [
            str(m.user_id) for m in members
            if manager.is_user_online_globally(m.user_id)
        ]
        await websocket.send_text(json.dumps({
            "event": "presence.initial",
            "data": {
                "chat_id": str(chat_id),
                "online_user_ids": online_members,
            }
        }))

        if first_connection:
            await manager.broadcast_to_chat(
                chat_id,
                json.dumps({
                    "event": "presence.online",
                    "data": {
                        "chat_id": str(chat_id),
                        "user_id": str(current_user.user_id),
                    },
                }),
                exclude_user=current_user.user_id,
            )
            # Global broadcast
            await broadcast_presence_to_global(
                chat_id=chat_id,
                user_id=current_user.user_id,
                status="online",
                db=db
            )

        while True:
            raw = await websocket.receive_text()

            try:
                packet = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "data": {"message": "Invalid JSON"}
                }))
                continue

            event = packet.get("event")
            data = packet.get("data") or {}

            # ==================== PING ====================
            if event == "ping":
                ok = await validate_and_touch_activity(
                    db=db,
                    session_repo=session_repo,
                    user_repo=user_repo,
                    session_id=current_session_id,
                    user_id=current_user.user_id,
                )
                if not ok:
                    await websocket.close(code=1008)
                    return

                await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                continue

            # ==================== TYPING ====================
            if event == "typing":
                ok = await validate_and_touch_activity(
                    db=db, session_repo=session_repo, user_repo=user_repo,
                    session_id=current_session_id, user_id=current_user.user_id
                )
                if not ok:
                    await websocket.close(code=1008)
                    return

                await manager.broadcast_to_chat(
                    chat_id,
                    json.dumps({
                        "event": "typing",
                        "data": {
                            "chat_id": str(chat_id),
                            "user_id": str(current_user.user_id),
                            "is_typing": bool(data.get("is_typing", True)),
                        },
                    }),
                    exclude_user=current_user.user_id,
                )

                # Global broadcast
                await broadcast_typing_to_global(
                    chat_id=chat_id,
                    user_id=current_user.user_id,
                    is_typing=bool(data.get("is_typing", True)),
                    db=db
                )
                continue

            # ==================== MESSAGE SEND ====================
            if event == "message.send":
                ok = await validate_and_touch_activity(
                    db=db, session_repo=session_repo, user_repo=user_repo,
                    session_id=current_session_id, user_id=current_user.user_id
                )
                if not ok:
                    await websocket.close(code=1008)
                    return

                msg = await service.send_message(
                    chat_id=chat_id,
                    sender_id=current_user.user_id,
                    client_message_id=data.get("client_message_id"),
                    content_type=data.get("content_type", "TEXT"),
                    text_content=data.get("text_content"),
                    metadata_json=data.get("metadata_json"),
                    reply_to_message_id=uuid.UUID(data["reply_to_message_id"]) if data.get("reply_to_message_id") else None,
                    attachment_ids=[uuid.UUID(x) for x in (data.get("attachment_ids") or [])],
                    is_silent=bool(data.get("is_silent", False)),
                    scheduled_at=None,
                )

                # ACK to sender
                ack = {
                    "event": "message.ack",
                    "data": {
                        "client_message_id": data.get("client_message_id"),
                        "message_id": str(msg.message_id),
                        "created_at": msg.created_at.isoformat(),
                    },
                }
                await websocket.send_text(json.dumps(ack))

                # Broadcast to chat members (per-chat socket)
                created = {
                    "event": "message.created",
                    "data": {
                        "chat_id": str(chat_id),
                        "message_id": str(msg.message_id),
                        "sender_id": str(current_user.user_id),
                        "content_type": msg.content_type,
                        "text_content": msg.text_content,
                        "created_at": msg.created_at.isoformat(),
                        "client_message_id": data.get("client_message_id"),
                    },
                }
                await manager.broadcast_to_chat(
                    chat_id, json.dumps(created), exclude_user=current_user.user_id
                )

                # NEW: Global broadcast for Sidebar live update
                await broadcast_new_message_to_global(
                    chat_id=chat_id,
                    message=msg,
                    sender_id=current_user.user_id,
                    db=db
                )
                continue

            # ==================== MESSAGE READ ====================
            if event == "message.read":
                ok = await validate_and_touch_activity(
                    db=db, session_repo=session_repo, user_repo=user_repo,
                    session_id=current_session_id, user_id=current_user.user_id
                )
                if not ok:
                    await websocket.close(code=1008)
                    return

                message_id = data.get("message_id")
                if message_id:
                    await service.mark_read(
                        chat_id=chat_id,
                        user_id=current_user.user_id,
                        message_id=uuid.UUID(message_id),
                    )

                    await manager.broadcast_to_chat(
                        chat_id,
                        json.dumps({
                            "event": "message.read",
                            "data": {
                                "chat_id": str(chat_id),
                                "user_id": str(current_user.user_id),
                                "message_id": message_id,
                            },
                        }),
                        exclude_user=current_user.user_id,
                    )

                    await broadcast_read_to_global(
                        chat_id=chat_id,
                        reader_id=current_user.user_id,
                        message_id=message_id,
                        db=db
                    )
            # ==================== CALL EVENTS ====================
            if event in ("call.offer", "call.answer", "call.reject", "call.end", "call.ice_candidate"):
                try:
                    full_name = f"{getattr(current_user, 'first_name', '') or ''} {getattr(current_user, 'last_name', '') or ''}".strip()
                    caller_name = full_name or getattr(current_user, "username", "") or "کاربر"
                    caller_avatar = getattr(current_user, "profile_url", None)
                    call_payload = {
                        "event": event,
                        "data": {
                            "chat_id": str(chat_id),
                            "caller_id": str(current_user.user_id),
                            "caller_name": caller_name,
                            "caller_avatar_url": caller_avatar,
                            **data,
                        },
                    }
                    call_json = json.dumps(call_payload)
                    await manager.broadcast_to_chat(
                        chat_id, call_json, exclude_user=current_user.user_id
                    )
                    members = await repo.get_all_active_members(chat_id)
                    for member in members:
                        if member.user_id != current_user.user_id:
                            await manager.send_to_user_global(member.user_id, call_json)
                except Exception as call_err:
                    print(f"[Chat WS Call Error] {call_err}")
                continue

            await websocket.send_text(json.dumps({
                "event": "error",
                "data": {"message": f"Unsupported event: {event}"}
            }))

    except WebSocketDisconnect:
        pass

    finally:
        if connected:
            is_now_offline = manager.disconnect(
                chat_id=chat_id,
                user_id=current_user.user_id,
                websocket=websocket,
            )

            if is_now_offline:
                try:
                    await user_repo.touch_last_seen(user_id=current_user.user_id)
                    await db.commit()
                except Exception:
                    await db.rollback()

                await manager.broadcast_to_chat(
                    chat_id,
                    json.dumps({
                        "event": "presence.offline",
                        "data": {
                            "chat_id": str(chat_id),
                            "user_id": str(current_user.user_id),
                        },
                    }),
                    exclude_user=current_user.user_id,
                )
                await broadcast_presence_to_global(
                    chat_id=chat_id,
                    user_id=current_user.user_id,
                    status="offline",
                    db=db
                )


# ============================================================
# Global Broadcasting Helper Functions
# ============================================================

async def broadcast_new_message_to_global(
    chat_id: UUID, 
    message, 
    sender_id: UUID,
    db: AsyncSession
):
    """ارسال رویداد پیام جدید به Global Socket تمام اعضای چت (به جز فرستنده)"""
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)
        print("00000000000000000000")
        print(members)
        
        if not members:
            return

        event = {
            "event": "new_message",
            "data": {
                "chat_id": str(chat_id),
                "message_id": str(message.message_id),
                "sender_id": str(sender_id),
                "content_type": message.content_type,
                "text_content": getattr(message, 'text_content', None),
                "created_at": message.created_at.isoformat(),
                "unread_increment": True,
            }
        }
        event_json = json.dumps(event)

        for member in members:
            # if member.user_id != sender_id:
                await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        # Silent error logging to prevent websocket crash
        print(f"[Global Broadcast Error] new_message: {e}")


async def broadcast_read_to_global(
    chat_id: UUID, 
    reader_id: UUID, 
    message_id: str,
    db: AsyncSession
):
    """Broadcast read receipt event to global socket"""
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)

        event = {
            "event": "message.read",
            "data": {
                "chat_id": chat_id,
                "user_id": reader_id,
                "message_id": message_id,
            }
        }
        event_json = json.dumps(event, default=str)

        for member in members:
            await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] message.read: {e}")


async def broadcast_typing_to_global(
    chat_id: UUID, 
    user_id: UUID, 
    is_typing: bool,
    db: AsyncSession
):
    """Broadcast typing status to global socket of other members"""
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)

        event = {
            "event": "typing",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(user_id),
                "is_typing": is_typing,
            }
        }
        event_json = json.dumps(event)

        for member in members:
            if str(member.user_id) != str(user_id):
                await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] typing: {e}")


async def broadcast_presence_to_global(
    chat_id: UUID, 
    user_id: UUID, 
    status: str,   # "online" or "offline"
    db: AsyncSession
):
    """Broadcast presence status (online/offline) to global socket of other members"""
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)

        event = {
            "event": f"presence.{status}",
            "data": {
                "chat_id": str(chat_id),
                "user_id": str(user_id),
            }
        }
        event_json = json.dumps(event)

        for member in members:
            if str(member.user_id) != str(user_id):
                await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] presence.{status}: {e}")


async def broadcast_presence_for_user_chats(
    user_id: UUID,
    status: str,   # "online" or "offline"
    db: AsyncSession
):
    """ارسال وضعیت حضور کاربر به چت‌ها و سوکت‌های جهانی تمام هم‌صحبت‌های وی"""
    try:
        repo = ChatRepository(db)
        chats = await repo.list_user_chats(user_id=user_id, limit=200, archived=None)
        notified_users = set()
        for chat_row in chats:
            chat = chat_row[0] if isinstance(chat_row, (tuple, list)) else chat_row
            chat_id = chat.chat_id

            event = {
                "event": f"presence.{status}",
                "data": {
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                }
            }
            # Chat WS broadcast
            await manager.broadcast_to_chat(
                chat_id,
                json.dumps(event),
                exclude_user=user_id,
            )

            # Global WS broadcast to other members
            members = await repo.get_all_active_members(chat_id)
            event_json = json.dumps(event)
            for m in members:
                if m.user_id != user_id and m.user_id not in notified_users:
                    notified_users.add(m.user_id)
                    await manager.send_to_user_global(m.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] broadcast_presence_for_user_chats {status}: {e}")

async def broadcast_update_message_to_global(
    chat_id: UUID, 
    message_id: str, 
    text_content: Optional[str],
    edited_at: Optional[str],
    db: AsyncSession
):
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)

        event = {
            "event": "message.updated",
            "data": {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "text_content": text_content,
                "edited_at": edited_at,
            }
        }
        event_json = json.dumps(event)

        for member in members:
            await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] message.updated: {e}")

async def broadcast_delete_message_to_global(
    chat_id: UUID, 
    message_id: str, 
    db: AsyncSession
):
    try:
        repo = ChatRepository(db)
        members = await repo.get_all_active_members(chat_id)

        event = {
            "event": "message.deleted",
            "data": {
                "chat_id": str(chat_id),
                "message_id": message_id,
            }
        }
        event_json = json.dumps(event)

        for member in members:
            await manager.send_to_user_global(member.user_id, event_json)

    except Exception as e:
        print(f"[Global Broadcast Error] message.deleted: {e}")
