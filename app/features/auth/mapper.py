from uuid import UUID

from app.features.auth.models import UserSession
from app.features.auth.schemas import (
    SessionLocationResponse,
    UserSessionResponse,
)


def map_session_to_response(
    session: UserSession,
    current_session_id: UUID,
) -> UserSessionResponse:
    location = None

    if session.country_code or session.country_name or session.city_name:
        location = SessionLocationResponse(
            country_code=session.country_code,
            country_name=session.country_name,
            city_name=session.city_name,
            timezone=session.timezone,
        )

    return UserSessionResponse(
        user_session_id=session.user_session_id,
        is_current=session.user_session_id == current_session_id,

        device_name=session.device_name,
        device_type=session.device_type,
        device_brand=session.device_brand,
        device_model=session.device_model,

        os_name=session.os_name,
        os_version=session.os_version,

        browser_name=session.browser_name,
        browser_version=session.browser_version,

        ip_address=session.ip_address,
        location=location,

        remember=session.remember,

        created_at=session.created_at,
        last_active_at=session.last_active_at,
        expires_at=session.expires_at,
    )
