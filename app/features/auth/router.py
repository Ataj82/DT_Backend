from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status, Cookie, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm
from app.features.users.schemas import UserCreate, UserResponse, Token
from app.core.config import settings
from types import SimpleNamespace



from app.api.dependencies import get_auth_service, get_current_user, get_db, get_current_session_payload
from app.features.auth.schemas import (
    LoginRequest,
    ExternalLoginRequest,
    LoginResponse,
    RefreshResponse,
    MessageResponse,
    SessionResponse,
    MeResponse,
    RegisterRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    GoogleLoginRequest,
)
from app.features.auth.services import AuthService
from app.features.users.models import User

router = APIRouter()

REFRESH_COOKIE_KEY = "refresh_token"
REFRESH_COOKIE_PATH = "/"
REFRESH_COOKIE_HTTPONLY = True
REFRESH_COOKIE_SAMESITE = "lax"
REFRESH_COOKIE_SECURE = False  # change to True in production with HTTPS


def set_refresh_cookie(response: Response, refresh_token: str, max_age: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=refresh_token,
        max_age=max_age,
        httponly=REFRESH_COOKIE_HTTPONLY,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_KEY,
        path=REFRESH_COOKIE_PATH,
    )


def get_current_user_id(user: User) -> UUID:
    user_id = getattr(user, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing",
        )
    return UUID(str(user_id))



@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.register(payload, request)

    set_refresh_cookie(
        response=response,
        refresh_token=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
    )

    return LoginResponse(
        access_token=result["access_token"],
        token_type="bearer",
        expires_in=result["access_token_expires_in"],
        user=result["user"],
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.login(payload, request)

    set_refresh_cookie(
        response=response,
        refresh_token=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
    )

    return LoginResponse(
        access_token=result["access_token"],
        token_type="bearer",
        expires_in=result["access_token_expires_in"],
        user=result["user"],
    )


@router.post("/external-login", status_code=status.HTTP_200_OK)
async def external_login(
    payload: ExternalLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.external_login(payload, request)

    set_refresh_cookie(
        response=response,
        refresh_token=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
    )

    return {
        "access_token": result["access_token"],
        "token_type": "bearer",
        "expires_in": result["access_token_expires_in"],
        "user": result["user"],
        "role": result["role"],
        "token": result["access_token"],
    }


@router.post("/google", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login_google(
    payload: GoogleLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.login_with_google(payload, request)

    set_refresh_cookie(
        response=response,
        refresh_token=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
    )

    return LoginResponse(
        access_token=result["access_token"],
        token_type="bearer",
        expires_in=result["access_token_expires_in"],
        user=result["user"],
    )


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_KEY),
    service: AuthService = Depends(get_auth_service),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing",
        )

    result = await service.refresh(refresh_token, request)

    set_refresh_cookie(
        response=response,
        refresh_token=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
    )

    return RefreshResponse(
        access_token=result["access_token"],
        token_type="bearer",
        expires_in=result["access_token_expires_in"],
    )


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_KEY),
    service: AuthService = Depends(get_auth_service),
):
    if refresh_token:
        await service.logout(refresh_token)

    clear_refresh_cookie(response)

    return MessageResponse(message="Logged out successfully")

@router.get("/me/sessions", status_code=status.HTTP_200_OK)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    current_session: dict = Depends(get_current_session_payload),
    service: AuthService = Depends(get_auth_service),
):
    return current_session

@router.get("/sessions", response_model=list[SessionResponse], status_code=status.HTTP_200_OK)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    user_id = get_current_user_id(current_user)
    return await service.get_user_sessions(user_id)


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def me(
    current_user: User = Depends(get_current_user),
):
    return {
        "user": current_user
    }

@router.post("/logout-all", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    user_id = get_current_user_id(current_user)
    await service.logout_all(user_id=user_id)

    clear_refresh_cookie(response)

    return MessageResponse(message="Logged out from all sessions successfully")

@router.delete("/sessions/{session_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    user_id = get_current_user_id(current_user)
    await service.revoke_session(user_id=user_id, session_id=session_id)

    return MessageResponse(message="Session revoked successfully")

@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    await service.forgot_password(payload)

    return MessageResponse(
        message="If the account exists, a password reset link has been sent"
    )

@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    await service.reset_password(payload)

    return MessageResponse(message="Password has been reset successfully")


@router.post("/login_swagger", response_model=Token, status_code=status.HTTP_200_OK)
async def login_swagger(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db=db)

    payload = SimpleNamespace(
        username=form_data.username,
        password=form_data.password,
        remember=False,
        device_name="Swagger",
    )

    result = await service.login(
        payload=payload,
        request=request,
    )

    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=result["refresh_token"],
        max_age=result["refresh_token_max_age"],
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
    )

    return {
        "access_token": result["access_token"],
        "token_type": "bearer",
    }
