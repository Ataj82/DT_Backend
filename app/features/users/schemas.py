from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, UUID4, EmailStr

class UserBase(BaseModel):
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    user_type: str = "STUDENT"

class UserCreate(UserBase):
    password: str

class UserProfilePhotoResponse(BaseModel):
    photo_id: UUID4
    photo_url: str
    is_primary: bool = False
    order: int = 0
    created_at: datetime

    class Config:
        from_attributes = True

class UserResponse(UserBase):
    user_id: UUID4
    profile_url: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    is_active: bool
    profile_photos: List[UserProfilePhotoResponse] = []

    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class UserSettingsPayload(BaseModel):
    chat: Optional[dict] = None
    appearance: Optional[dict] = None
    notifications: Optional[dict] = None
    privacy: Optional[dict] = None
    dataStorage: Optional[dict] = None
    theme: Optional[str] = None
    language: Optional[str] = None


class ContactUserResponse(BaseModel):
    user_id: UUID4
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_url: Optional[str] = None
    bio: Optional[str] = None
    user_type: str = "STUDENT"
    last_seen_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContactResponse(BaseModel):
    contact_id: UUID4
    contact_user_id: UUID4
    custom_name: Optional[str] = None
    created_at: datetime
    user: ContactUserResponse

    class Config:
        from_attributes = True


class ContactCreate(BaseModel):
    username: Optional[str] = None
    contact_user_id: Optional[UUID4] = None
    custom_name: Optional[str] = None


class ContactUpdate(BaseModel):
    custom_name: Optional[str] = None


class UserSearchResult(BaseModel):
    user_id: UUID4
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_url: Optional[str] = None
    bio: Optional[str] = None
    user_type: str = "STUDENT"
    last_seen_at: Optional[datetime] = None
    is_contact: bool = False

    class Config:
        from_attributes = True
