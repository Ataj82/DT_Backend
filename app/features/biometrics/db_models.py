"""
SQLAlchemy Database Model for Persistent Biometric Profiles.
Persists enrolled face embeddings (512-D), Gaze weights, and Neutral baseline vectors in PostgreSQL.
"""

import sqlalchemy as sa
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.core.database import Base


class UserBiometricProfile(Base):
    __tablename__ = "user_biometric_profiles"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id = Column(String, unique=True, nullable=False, index=True)

    # Face Enrollment (ArcFace 512-D embedding)
    is_enrolled = Column(Boolean, default=False, nullable=False)
    enrolled_at = Column(DateTime(timezone=True), nullable=True)
    face_embedding = Column(JSONB, nullable=True)
    liveness_status = Column(String, nullable=True, default="genuine")

    # Gaze & Head Pose Calibration
    is_gaze_calibrated = Column(Boolean, default=False, nullable=False)
    gaze_calibrated_at = Column(DateTime(timezone=True), nullable=True)
    gaze_samples_count = Column(Integer, default=0, nullable=False)
    gaze_weights = Column(JSONB, nullable=True)

    # 3-Second Neutral Baseline Affect Calibration
    is_neutral_calibrated = Column(Boolean, default=False, nullable=False)
    neutral_calibrated_at = Column(DateTime(timezone=True), nullable=True)
    neutral_samples_count = Column(Integer, default=0, nullable=False)
    neutral_baseline_mean = Column(JSONB, nullable=True)
    neutral_baseline_std = Column(JSONB, nullable=True)

    # Administrative Edit Permission (True = student can reset/edit; False = locked by admin)
    can_edit = Column(Boolean, default=True, nullable=False)

    # Timestamps
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

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "is_enrolled": self.is_enrolled,
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
            "liveness": self.liveness_status or "genuine",
            "is_gaze_calibrated": self.is_gaze_calibrated,
            "gaze_calibrated_at": self.gaze_calibrated_at.isoformat() if self.gaze_calibrated_at else None,
            "gaze_samples_count": self.gaze_samples_count,
            "is_neutral_calibrated": self.is_neutral_calibrated,
            "neutral_calibrated_at": self.neutral_calibrated_at.isoformat() if self.neutral_calibrated_at else None,
            "neutral_samples_count": self.neutral_samples_count,
            "has_face_embedding": self.face_embedding is not None,
            "has_gaze_weights": self.gaze_weights is not None,
            "has_neutral_baseline": self.neutral_baseline_mean is not None,
            "can_edit": bool(self.can_edit),
        }
