from __future__ import annotations

import logging
from fastapi import Depends, Header, HTTPException, status

from .dependencies import get_framework
from ..multiuser.models import User, UserRole

logger = logging.getLogger(__name__)


def get_multiuser_service():
    return get_framework().services.multi_user_service


async def get_current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()

    svc = get_multiuser_service()

    # 1. Try internal pipeline JWT token first
    try:
        return svc.authenticate(token)
    except Exception:
        pass

    # 2. Try host backend JWT token
    try:
        import uuid
        from app.core.security import decode_token
        from app.core.database import async_session
        from app.features.users.repository import UserRepository

        payload = decode_token(token)
        user_id = str(payload.get("sub") or payload.get("user_id") or "")
        if user_id:
            role = None
            display_name = str(payload.get("name") or payload.get("username") or "")
            email = str(payload.get("email") or f"{user_id}@dt.internal")

            # Look up in host database to get actual role and display name
            try:
                u_uuid = uuid.UUID(user_id)
                async with async_session() as session:
                    repo = UserRepository(session)
                    db_user = await repo.get_by_id(u_uuid)
                    if db_user:
                        if db_user.user_type and db_user.user_type.upper() in {"TEACHER", "ADMIN", "PROFESSOR", "INSTRUCTOR"}:
                            role = UserRole.PROFESSOR
                        else:
                            role = UserRole.STUDENT
                        if not display_name:
                            full_name = f"{db_user.first_name or ''} {db_user.last_name or ''}".strip()
                            display_name = full_name or db_user.username
                        if db_user.username and "@" in db_user.username:
                            email = db_user.username
            except Exception as db_err:
                logger.debug("Could not fetch user from DB in pipeline auth bridge: %s", db_err)

            if role is None:
                role_str = str(payload.get("role") or "").lower()
                role = UserRole.PROFESSOR if role_str in {"teacher", "professor", "instructor", "admin"} else UserRole.STUDENT

            if not display_name:
                display_name = email.split("@")[0] or user_id

            # Check if user already registered in pipeline repository
            existing = svc.repository.get_user(user_id)
            if existing:
                existing.role = role
                if display_name:
                    existing.display_name = display_name
                return existing

            # Ensure host user exists in pipeline in-memory repository
            bridged_user = User(
                id=user_id,
                email=email,
                display_name=display_name,
                password_hash="",
                role=role,
            )
            svc.repository.save_user(bridged_user)
            return bridged_user
    except Exception as exc:
        logger.debug("Host token decode failed: %s", exc)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_professor(user: User = Depends(get_current_user)) -> User:
    if user.role not in {UserRole.PROFESSOR, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Professor access required.")
    return user


def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required.")
    return user
