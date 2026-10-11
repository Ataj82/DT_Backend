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


@router.get("/login-directory", status_code=status.HTTP_200_OK)
async def get_login_directory(db: AsyncSession = Depends(get_db)):
    """
    Public directory of courses, teachers, and enrolled students for dynamic portal login.
    Enables choosing any course and seeing its specific instructor and student roster.
    """
    from sqlalchemy import select
    from app.features.lessons.models import Lesson, LessonMember
    from app.features.courses.router import COURSE_METADATA

    stmt = select(Lesson).order_by(Lesson.created_at.asc())
    result = await db.execute(stmt)
    lessons = result.scalars().all()

    directory = []
    for lesson in lessons:
        teacher_info = None
        if lesson.teacher_id:
            stmt_t = select(User).where(User.user_id == lesson.teacher_id)
            res_t = await db.execute(stmt_t)
            t_user = res_t.scalar_one_or_none()
            if t_user:
                t_name = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.username
                teacher_info = {
                    "id": str(t_user.user_id),
                    "name": t_name,
                    "username": t_user.username,
                    "role": "TEACHER",
                    "defaultToken": f"sso_token_{t_user.username}",
                    "avatar": t_user.profile_url,
                }

        if not teacher_info:
            teacher_info = {
                "id": "10000000-0000-4000-8000-000000000001",
                "name": "دکتر محمد اله بخش",
                "username": "mohammad_allahbakhsh",
                "role": "TEACHER",
                "defaultToken": "sso_token_dr_allahbakhsh",
                "avatar": None,
            }

        stmt_students = (
            select(User)
            .join(LessonMember, LessonMember.user_id == User.user_id)
            .where(
                LessonMember.lesson_id == lesson.lesson_id,
                User.user_type == "STUDENT",
            )
            .order_by(User.first_name.asc(), User.last_name.asc())
        )
        res_students = await db.execute(stmt_students)
        student_users = res_students.scalars().all()

        students_list = []
        for s in student_users:
            s_name = f"{s.first_name or ''} {s.last_name or ''}".strip() or s.username
            students_list.append({
                "id": str(s.user_id),
                "name": s_name,
                "username": s.username,
                "role": "STUDENT",
                "defaultToken": f"sso_token_{s.username}",
                "avatar": s.profile_url,
            })

        meta = COURSE_METADATA.get(lesson.lesson_id, {})
        directory.append({
            "id": str(lesson.lesson_id),
            "title": lesson.title,
            "department": meta.get("department", "مهندسی کامپیوتر"),
            "degree": meta.get("degree", "کارشناسی"),
            "units": meta.get("units", 3),
            "teacher": teacher_info,
            "students": students_list,
        })

    if not directory:
        directory.append({
            "id": "c0000000-0000-4000-8000-000000000001",
            "title": "سیستم عامل",
            "department": "مهندسی کامپیوتر",
            "degree": "کارشناسی",
            "units": 3,
            "teacher": {
                "id": "10000000-0000-4000-8000-000000000001",
                "name": "دکتر محمد اله بخش",
                "username": "mohammad_allahbakhsh",
                "role": "TEACHER",
                "defaultToken": "sso_token_dr_allahbakhsh",
                "avatar": None,
            },
            "students": [],
        })

    return directory

