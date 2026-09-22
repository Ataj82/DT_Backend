# app/features/chat/constants.py

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
    "DOCUMENT",
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

JOIN_REQUEST_STATUS = {
    "PENDING",
    "APPROVED",
    "REJECTED",
}
