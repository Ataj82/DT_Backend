from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import decode_token
from app.features.auth.services import AuthService
from app.features.users.models import User
from app.features.users.repository import UserRepository

# Swagger/OpenAPI bearer token endpoint
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/bot/v1/api/v1/auth/login_swagger",
    auto_error=False,
)


async def get_db() -> AsyncSession:
    async for session in get_async_db():
        yield session


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    return AuthService(db)


async def get_current_session_payload(
    token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
) -> dict:
    raw_token = token or query_token

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not raw_token:
        raise credentials_exception

    try:
        payload = decode_token(raw_token)

        token_type = payload.get("type")
        user_id = payload.get("sub")
        user_session_id = payload.get("user_session_id")

        if token_type != "access":
            raise credentials_exception

        if not user_id or not user_session_id:
            raise credentials_exception

        return {
            "user_id": UUID(user_id),
            "user_session_id": UUID(user_session_id),
            "payload": payload,
        }

    except Exception:
        raise credentials_exception


async def get_current_user(
    session_payload: dict = Depends(get_current_session_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_repo = UserRepository(db)
    user_id: UUID = session_payload["user_id"]

    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user
