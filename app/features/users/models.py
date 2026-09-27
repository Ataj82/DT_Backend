import sqlalchemy as sa
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    @property
    def id(self):
        return self.user_id

    @id.setter
    def id(self, val):
        self.user_id = val


    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    profile_url = Column(String, nullable=True)

    user_type = Column(String, nullable=False)  # STUDENT / TEACHER / BOT

    last_seen_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    is_active = Column(Boolean, default=True, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    # user settings & preferences
    theme = Column(String, default="light", nullable=True)
    language = Column(String, default="fa", nullable=True)

    # password reset
    reset_password_token = Column(String, nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    lessons_taught = relationship(
        "Lesson",
        foreign_keys="[Lesson.teacher_id]",
        back_populates="teacher",
    )
    # bot_sessions = relationship("BotSession", back_populates="student")
    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    profile_photos = relationship(
        "UserProfilePhoto",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(UserProfilePhoto.is_primary), desc(UserProfilePhoto.created_at)",
    )
    contacts_entries = relationship(
        "UserContact",
        foreign_keys="[UserContact.user_id]",
        cascade="all, delete-orphan",
        back_populates="user",
    )


class UserProfilePhoto(Base):
    __tablename__ = "user_profile_photos"

    photo_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id = Column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_url = Column(String, nullable=False)
    storage_key = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    order = Column(sa.Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="profile_photos")


class UserContact(Base):
    __tablename__ = "user_contacts"

    contact_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id = Column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_user_id = Column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    custom_name = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "contact_user_id", name="uq_user_contact"),
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="contacts_entries")
    contact_user = relationship("User", foreign_keys=[contact_user_id])
