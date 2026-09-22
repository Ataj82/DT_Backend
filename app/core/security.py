from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from app.core.config import settings
import hashlib
import secrets
from typing import Any


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    user_session_id: str,
    expires_delta: timedelta | None = None,
    extra_data: dict[str, Any] | None = None,
) -> str:
    """
    Create JWT access token.

    subject: user_id as string
    user_session_id: session UUID as string
    extra_data: optional additional claims
    """

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "user_session_id": str(user_session_id),
        "exp": expire,
        "type": "access",
    }

    if extra_data:
        to_encode.update(extra_data)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.PyJWTError:
        raise ValueError("Invalid token")


def create_refresh_token() -> str:
    """
    Refresh token خام.
    این مقدار فقط به cookie می‌رود و در دیتابیس ذخیره نمی‌شود.
    """
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """
    دیتابیس فقط hash refresh token را نگه می‌دارد.
    Pepper باعث می‌شود اگر دیتابیس لو رفت، توکن‌ها قابل استفاده نباشند.
    """
    value = f"{token}.{settings.REFRESH_TOKEN_PEPPER}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
    