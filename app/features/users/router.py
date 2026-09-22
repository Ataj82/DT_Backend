import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, create_access_token
from app.features.users.schemas import (
    UserCreate,
    UserResponse,
    Token,
    UserSettingsPayload,
    UserProfileUpdate,
    UserProfilePhotoResponse,
    ContactResponse,
    ContactCreate,
    ContactUpdate,
    UserSearchResult,
)
from app.features.users.services import UserService
from app.features.users.repository import UserRepository
from app.api.dependencies import get_db, get_current_user
from app.features.users.models import User
from app.core.redis import get_redis

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    service = UserService(db)
    return await service.create_user(user_data)


@router.post("/login_swagger", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.user_id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_user_with_photos(current_user.user_id)
    return user or current_user


@router.patch("/me", response_model=UserResponse)
async def update_users_me(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.update_profile(current_user.user_id, payload)


# ============================================================
# Profile Photos Management (Multi-Photo Support)
# ============================================================

@router.get("/me/photos", response_model=List[UserProfilePhotoResponse])
async def get_my_photos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.get_user_photos(current_user.user_id)


@router.post("/me/photos", response_model=UserProfilePhotoResponse)
async def upload_my_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.upload_profile_photo(current_user.user_id, file)


@router.delete("/me/photos/{photo_id}")
async def delete_my_photo(
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.delete_profile_photo(photo_id, current_user.user_id)


@router.patch("/me/photos/{photo_id}/primary", response_model=UserProfilePhotoResponse)
async def set_primary_my_photo(
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.set_primary_photo(photo_id, current_user.user_id)


# ============================================================
# Contacts Management
# ============================================================

@router.get("/contacts", response_model=List[ContactResponse])
async def get_my_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.get_user_contacts(current_user.user_id)


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def add_contact(
    payload: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.add_user_contact(current_user.user_id, payload)


@router.delete("/contacts/{contact_user_id}")
async def delete_contact(
    contact_user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.delete_user_contact(current_user.user_id, contact_user_id)


@router.patch("/contacts/{contact_user_id}", response_model=ContactResponse)
async def update_contact(
    contact_user_id: uuid.UUID,
    payload: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.update_user_contact(current_user.user_id, contact_user_id, payload)


# ============================================================
# User Search (Directory)
# ============================================================

@router.get("/search", response_model=List[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.search_users(current_user.user_id, q)


# ============================================================
# Other Users Profile & Privacy
# ============================================================

@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.get_user_profile_with_privacy(
        target_user_id=user_id,
        viewer_id=current_user.user_id
    )


@router.get("/{user_id}/photos", response_model=List[UserProfilePhotoResponse])
async def get_user_photos(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.get_user_photos_with_privacy(
        target_user_id=user_id,
        viewer_id=current_user.user_id
    )


# ============================================================
# User Settings & Preferences
# ============================================================

@router.get("/me/settings")
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_data = {
        "theme": current_user.theme or "light",
        "language": current_user.language or "fa",
        "appearance": {"theme": current_user.theme or "light"},
    }

    redis = get_redis()
    if redis:
        key = f"user:settings:{current_user.user_id}"
        raw = await redis.get(key)
        if raw:
            try:
                redis_data = json.loads(raw)
                current_data.update(redis_data)
            except Exception:
                pass
    
    return current_data


@router.patch("/me/settings")
async def update_user_settings(
    payload: UserSettingsPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Update Database fields
    if payload.theme is not None:
        current_user.theme = payload.theme
    elif payload.appearance and "theme" in payload.appearance:
        current_user.theme = payload.appearance["theme"]

    if payload.language is not None:
        current_user.language = payload.language

    await db.commit()

    # 2. Update Redis Cache
    redis = get_redis()
    key = f"user:settings:{current_user.user_id}"
    current_data = {
        "theme": current_user.theme or "light",
        "language": current_user.language or "fa",
        "appearance": {"theme": current_user.theme or "light"},
    }

    if redis:
        raw = await redis.get(key)
        if raw:
            try:
                current_data = json.loads(raw)
            except Exception:
                current_data = {}

    # Merge payload
    new_data = payload.model_dump(exclude_unset=True)
    for k, v in new_data.items():
        if isinstance(v, dict) and isinstance(current_data.get(k), dict):
            current_data[k].update(v)
        else:
            current_data[k] = v

    if redis:
        await redis.set(key, json.dumps(current_data))

    return current_data
