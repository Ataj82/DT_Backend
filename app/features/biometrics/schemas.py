"""
Pydantic Schemas for Biometric Authentication, Gaze Tracking & Affect Telemetry.
Includes schemas for Student Biometric Profile and Exam Distraction Proctoring.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


# --- Health & Monitoring ---

class HealthResponse(BaseModel):
    status: str = "healthy"
    enrolled_users_count: int = 0
    threshold: float = 0.65


# --- User Management ---

class UserListResponse(BaseModel):
    users: List[str]


class UserDeleteResponse(BaseModel):
    status: str
    user_id: str


# --- Face Authentication ---

class EnrollResponse(BaseModel):
    status: str
    user_id: str
    vector_size: int
    liveness: str
    liveness_details: Optional[Dict[str, Any]] = None


class VerifyResponse(BaseModel):
    verified: bool
    status: str
    cosine_distance: float
    threshold: float
    liveness: str
    liveness_details: Optional[Dict[str, Any]] = None
    user_id: str


# --- Gaze Calibration (9-Point Screen Grid / Head Turn) ---

class CalibrationSample(BaseModel):
    features: List[float] = Field(
        ...,
        description="7D feature vector [pitch_rad, yaw_rad, rx, ry, rz, gx, gy]"
    )
    target_norm: List[float] = Field(
        ...,
        description="2D normalized target on screen [norm_x, norm_y] in range [0, 1]"
    )


class CalibrationPayload(BaseModel):
    user_id: str
    samples: List[CalibrationSample] = Field(
        ...,
        description="List of 5 to 9 on-screen gaze target samples"
    )


class CalibrationResponse(BaseModel):
    status: str
    message: str
    user_id: str
    samples_count: int
    is_calibrated: bool


class CalibrationStatusResponse(BaseModel):
    user_id: str
    is_calibrated: bool
    samples_count: int = 0
    calibrated_at: Optional[float] = None


# --- Neutral Baseline Calibration (3-Second Affect Resting State) ---

class NeutralCalibrationPayload(BaseModel):
    user_id: str
    samples: List[List[float]] = Field(
        ...,
        description="List of 7D resting feature vectors [V, A, AU1, AU2, AU4, AU12, AU15]"
    )


class NeutralCalibrationResponse(BaseModel):
    status: str
    message: str
    user_id: str
    samples_count: int
    is_calibrated: bool


class NeutralCalibrationStatusResponse(BaseModel):
    user_id: str
    is_calibrated: bool
    duration_sec: float = 3.0
    samples_buffered: int = 0


# --- Biometric & Affect Telemetry ---

class ActionUnitsDict(BaseModel):
    AU01_inner_brow_raiser: float = 0.0
    AU02_outer_brow_raiser: float = 0.0
    AU04_brow_lowerer: float = 0.0
    AU12_lip_corner_puller: float = 0.0
    AU15_lip_corner_depress: float = 0.0
    AU45_blink_closure: float = 0.0


class TelemetryResponse(BaseModel):
    user_id: str
    record_id: Optional[int] = None
    dominant_emotion: str = "neutral"
    calibrated_mood: Optional[str] = "Normal"
    stress_score: float = 20.0
    status: str = "Normal"
    stress_classification: Optional[str] = "Normal"
    continuous_valence: float = 0.0
    continuous_arousal: float = 0.0
    affect_quadrant: str = "Q1"
    affect_quadrant_title: str = "Eustress / Flow & Engagement"
    action_units: Optional[Dict[str, float]] = None
    categorical_distribution: Optional[Dict[str, float]] = None
    emotions: Optional[Dict[str, float]] = None
    is_neutral_calibrated: bool = False
    blink_frequency_bpm: float = 0.0
    age: Optional[int] = None
    gender: Optional[str] = None
    gender_confidence: Optional[float] = None
    race: Optional[str] = None
    race_confidence: Optional[float] = None
    attention_score: float = 100.0
    attention_status: str = "Focused"
    is_focused: bool = True
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    gaze_direction: str = "Center"
    gaze_x_ratio: float = 0.5
    face_detected: bool = True
    face_box: Optional[List[int]] = None
    eyes_detected: Optional[int] = 0
    is_calibrated: bool = False
    gaze_features: Optional[List[float]] = None
    gaze_point: Optional[Dict[str, Any]] = None
    pose_vector: Optional[Dict[str, Any]] = None
    landmarks: Optional[Dict[str, Any]] = None
    self_test: Optional[Dict[str, Any]] = None


class TelemetryHistoryResponse(BaseModel):
    user_id: Optional[str] = None
    telemetry: List[Dict[str, Any]]


# --- Student Profile & Exam Distraction Telemetry ---

class StudentBiometricProfileStatus(BaseModel):
    user_id: str
    is_enrolled: bool = False
    face_enrolled: bool = False
    is_gaze_calibrated: bool = False
    gaze_calibrated: bool = False
    is_neutral_calibrated: bool = False
    neutral_calibrated: bool = False
    ready_for_exam: bool = False
    last_updated: Optional[str] = None
    last_calibrated_at: Optional[str] = None
    profile_details: Optional[Dict[str, Any]] = None


class ExamDistractionLogRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: str
    timestamp: Optional[Any] = None
    attention_score: float = 0.0
    gaze_direction: str = "Unfocused"
    dominant_emotion: Optional[str] = "neutral"
    stress_score: Optional[float] = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    duration_seconds: float = 2.0
    details: Optional[Dict[str, Any]] = None
    notes: Optional[str] = "Looked away from screen"


class ExamDistractionLogResponse(BaseModel):
    status: str = "recorded"
    session_id: str
    user_id: Optional[str] = None
    total_distractions: Optional[int] = 0
    total_distractions_count: Optional[int] = 0
    event: Optional[Dict[str, Any]] = None
