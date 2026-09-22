from datetime import datetime
from uuid import UUID
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    remember: bool = False


class ExternalLoginRequest(BaseModel):
    role: str = "TEACHER"
    token: Optional[str] = None
    username: Optional[str] = None
    remember: bool = True


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    username: str | None = None
    user_type: str | None = None
    email: str | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(TokenResponse):
    user: AuthUserResponse


class RefreshResponse(TokenResponse):
    pass


class SessionLocationResponse(BaseModel):
    country_code: str | None = None
    country_name: str | None = None
    city_name: str | None = None
    timezone: str | None = None


class UserSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_session_id: UUID
    is_current: bool

    device_name: str | None = None
    device_type: str | None = None
    device_brand: str | None = None
    device_model: str | None = None

    os_name: str | None = None
    os_version: str | None = None

    browser_name: str | None = None
    browser_version: str | None = None

    ip_address: str | None = None
    location: SessionLocationResponse | None = None

    remember: bool

    created_at: datetime
    last_active_at: datetime
    expires_at: datetime


class UserSessionListResponse(BaseModel):
    current_session: UserSessionResponse | None = None
    other_sessions: list[UserSessionResponse] = Field(default_factory=list)

class MessageResponse(BaseModel):
    message: str


from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_session_id: UUID
    user_id: UUID
    device_name: str | None = None
    device_type: str | None = None
    device_brand: str | None = None
    device_model: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    browser_name: str | None = None
    browser_version: str | None = None
    platform: str | None = None
    browser: str | None = None
    is_mobile: bool
    is_tablet: bool
    is_pc: bool
    is_bot: bool
    ip_address: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    city_name: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    user_agent: str | None = None
    remember: bool
    expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    last_active_at: datetime | None = None
    created_at: datetime



class SessionsResponse(BaseModel):
    sessions: List[SessionResponse]


class UserSchema(BaseModel):
    user_id: UUID
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    profile_url: str | None = None
    last_seen_at: datetime
    user_type: str
    created_at: datetime
    updated_at: datetime
    is_active: bool | None = None
    is_deleted: bool

class MeResponse(BaseModel):
    user: UserSchema

from pydantic import BaseModel, Field
from typing import Optional


class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    remember: bool = False
    user_type: str = "STUDENT"

class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class GoogleLoginRequest(BaseModel):
    credential: Optional[str] = None
    access_token: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    remember: bool = False
