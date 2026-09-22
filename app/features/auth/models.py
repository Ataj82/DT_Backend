import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Float,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    user_session_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    refresh_token_hash = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # Device info
    device_name = Column(String(255), nullable=True)

    device_type = Column(String(50), nullable=True)
    # desktop / mobile / tablet / bot / unknown

    device_brand = Column(String(100), nullable=True)
    device_model = Column(String(160), nullable=True)

    # OS info
    os_name = Column(String(100), nullable=True)
    os_version = Column(String(80), nullable=True)

    # Browser info
    browser_name = Column(String(100), nullable=True)
    browser_version = Column(String(80), nullable=True)

    is_mobile = Column(Boolean, default=False, nullable=False)
    is_tablet = Column(Boolean, default=False, nullable=False)
    is_pc = Column(Boolean, default=False, nullable=False)
    is_bot = Column(Boolean, default=False, nullable=False)

    # Network info
    ip_address = Column(String(64), nullable=True)

    country_code = Column(String(8), nullable=True)
    country_name = Column(String(120), nullable=True)
    city_name = Column(String(120), nullable=True)
    timezone = Column(String(120), nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Raw data
    user_agent = Column(Text, nullable=True)

    # Login/session options
    remember = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    last_active_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    revoke_reason = Column(String(80), nullable=True)

    user = relationship("User", back_populates="sessions")


Index(
    "ix_user_sessions_user_active",
    UserSession.user_id,
    UserSession.revoked_at,
    UserSession.expires_at,
)

Index(
    "ix_user_sessions_user_created",
    UserSession.user_id,
    UserSession.created_at,
)
