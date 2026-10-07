"""
Biometrics Master Router for DT FastAPI Core Backend.
Natively executes Face Authentication (ArcFace + MiniFASNet anti-spoofing),
Gaze & Head Pose Tracking (L2CS-Net MobileOne-S0 + Ridge regression polynomial),
3-Second Neutral Baseline Affect Engine (EfficientNet-B0 MTL + Russell Circumplex),
Real-time Video Telemetry, and Exam Distraction Logging directly in-process.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Query

from .config import (
    COSINE_THRESHOLD,
    DEFAULT_LIVENESS_MODE,
    DEFAULT_DETECTOR,
)
from .database import (
    save_face_embedding,
    get_face_embedding,
    delete_face_embedding,
    list_enrolled_users,
    update_student_profile,
    get_student_profile,
)
from .schemas import (
    EnrollResponse,
    VerifyResponse,
    UserListResponse,
    UserDeleteResponse,
    CalibrationPayload,
    CalibrationResponse,
    CalibrationStatusResponse,
    NeutralCalibrationPayload,
    NeutralCalibrationResponse,
    NeutralCalibrationStatusResponse,
    TelemetryResponse,
    TelemetryHistoryResponse,
    StudentBiometricProfileStatus,
    ExamDistractionLogRequest,
    ExamDistractionLogResponse,
)

# Native biometrics sub-engines
from .service import decode_image, process_live_frame, cosine_distance
from .attention import get_user_calibrator, reset_user_calibrator
from .emotion_engine import (
    get_affect_engine,
    reset_affect_engine,
    calibrate_user_neutral_baseline,
)
from .telemetry import (
    analyze_stress_and_emotion,
    log_telemetry_live,
    get_telemetry_history,
)

router = APIRouter(tags=["Biometrics"])
biometrics_router = router

# In-memory session distraction logs: session_id -> list of events
EXAM_DISTRACTIONS: Dict[str, List[Dict[str, Any]]] = {}


# ============================================================================
# 1. FACE AUTHENTICATION & ENROLLMENT (Native ArcFace + MiniFASNet)
# ============================================================================

@router.get("/users", response_model=UserListResponse)
def get_enrolled_users():
    """Returns a list of all currently enrolled user IDs from the native store."""
    return {"users": list_enrolled_users()}


@router.delete("/users/{user_id}", response_model=UserDeleteResponse)
def remove_user(user_id: str):
    """Deletes an enrolled face embedding and marks profile un-enrolled."""
    uid = user_id.strip()
    success = delete_face_embedding(uid)
    if success:
        update_student_profile(uid, {"is_enrolled": False})
        return {"status": "deleted", "user_id": uid}
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"User '{uid}' not found in biometric store."
    )


@router.post("/enroll", response_model=EnrollResponse)
async def enroll_face(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    liveness_mode: str = Form(DEFAULT_LIVENESS_MODE),
    detector: str = Form(DEFAULT_DETECTOR)
):
    """
    Enrolls a genuine human face using DeepFace ArcFace 512-D representation
    protected by MiniFASNet anti-spoofing verification natively in-process.
    """
    uid = user_id.strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID cannot be empty.")

    contents = await file.read()
    try:
        img = decode_image(contents)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    embedding, err, details = process_live_frame(img, detector=detector, liveness_mode=liveness_mode)
    if err:
        if "Spoof" in err or "presentation attack" in err.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Enrollment rejected: {err}"
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    save_face_embedding(uid, embedding)
    update_student_profile(uid, {
        "is_enrolled": True,
        "enrolled_at": datetime.utcnow().isoformat(),
        "vector_size": len(embedding),
        "liveness": "genuine" if liveness_mode != "off" else "bypassed"
    })

    return {
        "status": "enrolled",
        "user_id": uid,
        "vector_size": len(embedding),
        "liveness": "genuine" if liveness_mode != "off" else "bypassed",
        "liveness_details": details
    }


@router.post("/verify", response_model=VerifyResponse)
async def verify_face(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    liveness_mode: str = Form(DEFAULT_LIVENESS_MODE),
    detector: str = Form(DEFAULT_DETECTOR)
):
    """
    Verifies a live face against an enrolled template using ArcFace cosine distance
    and MiniFASNet presentation attack detection natively.
    """
    uid = user_id.strip()
    enrolled_embedding = get_face_embedding(uid)
    if enrolled_embedding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{uid}' is not enrolled. Please enroll first."
        )

    contents = await file.read()
    try:
        img = decode_image(contents)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    live_embedding, err, details = process_live_frame(img, detector=detector, liveness_mode=liveness_mode)
    if err:
        if "Spoof" in err or "presentation attack" in err.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    distance = cosine_distance(enrolled_embedding, live_embedding)
    is_match = bool(distance <= COSINE_THRESHOLD)

    return {
        "verified": is_match,
        "status": "ACCESS GRANTED" if is_match else "ACCESS DENIED",
        "cosine_distance": round(distance, 4),
        "threshold": COSINE_THRESHOLD,
        "liveness": "genuine" if liveness_mode != "off" else "bypassed",
        "liveness_details": details,
        "user_id": uid
    }


# ============================================================================
# 2. GAZE & HEAD MOVEMENT CALIBRATION ('نه نه')
# ============================================================================

@router.post("/calibrate", response_model=CalibrationResponse)
async def register_gaze_calibration(payload: CalibrationPayload):
    """
    Fits a personalized closed-form Ridge Regression polynomial model
    from calibration targets (including left-right 'نه نه' head movements).
    """
    uid = payload.user_id.strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID cannot be empty.")
    if len(payload.samples) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least 5 calibration samples required, got {len(payload.samples)}."
        )

    features = np.array([s.features for s in payload.samples], dtype=np.float64)
    targets = np.array([s.target_norm for s in payload.samples], dtype=np.float64)

    calibrator = get_user_calibrator(uid)
    success = calibrator.fit(features, targets)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to solve closed-form Ridge Regression for calibration."
        )

    update_student_profile(uid, {
        "is_gaze_calibrated": True,
        "gaze_calibrated_at": datetime.utcnow().isoformat(),
        "gaze_samples_count": len(payload.samples)
    })

    return {
        "status": "success",
        "message": f"Successfully calibrated {len(payload.samples)} points for user '{uid}'.",
        "user_id": uid,
        "samples_count": len(payload.samples),
        "is_calibrated": True
    }


@router.post("/calibrate/reset")
async def reset_gaze_calibration_endpoint(user_id: str = Form(...)):
    """Resets gaze calibration for a user back to default geometric estimation."""
    uid = user_id.strip()
    reset_user_calibrator(uid)
    update_student_profile(uid, {"is_gaze_calibrated": False})
    return {
        "status": "success",
        "message": f"Calibration reset for user '{uid}'.",
        "user_id": uid,
        "is_calibrated": False
    }


@router.get("/calibrate/status", response_model=CalibrationStatusResponse)
async def get_gaze_calibration_status_endpoint(user_id: str = Query(...)):
    """Returns current gaze calibration status for a user."""
    uid = user_id.strip()
    calibrator = get_user_calibrator(uid)
    return {
        "user_id": uid,
        "is_calibrated": calibrator.is_calibrated,
        "samples_count": calibrator.samples_count,
        "calibrated_at": calibrator.calibrated_at
    }


# ============================================================================
# 3. 3-SECOND NEUTRAL BASELINE EMOTION CALIBRATION
# ============================================================================

@router.post("/telemetry/calibrate_neutral", response_model=NeutralCalibrationResponse)
async def register_neutral_affect_calibration(payload: NeutralCalibrationPayload):
    """
    Fits personalized resting baseline over 3 seconds of resting frames,
    eliminating morphological resting face bias (e.g. natural brow furrows).
    """
    uid = payload.user_id.strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID cannot be empty.")
    if len(payload.samples) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least 5 resting neutral samples required, got {len(payload.samples)}."
        )

    success = calibrate_user_neutral_baseline(uid, payload.samples)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fit neutral baseline."
        )

    update_student_profile(uid, {
        "is_neutral_calibrated": True,
        "neutral_calibrated_at": datetime.utcnow().isoformat(),
        "neutral_samples_count": len(payload.samples)
    })

    return {
        "status": "success",
        "message": f"Successfully calibrated neutral baseline for user '{uid}'.",
        "user_id": uid,
        "samples_count": len(payload.samples),
        "is_calibrated": True
    }


@router.post("/telemetry/calibrate_neutral/reset")
async def reset_neutral_affect_calibration_endpoint(user_id: str = Form(...)):
    """Resets neutral baseline for a user."""
    uid = user_id.strip()
    reset_affect_engine(uid)
    update_student_profile(uid, {"is_neutral_calibrated": False})
    return {
        "status": "success",
        "message": f"Neutral baseline reset for user '{uid}'.",
        "user_id": uid,
        "is_calibrated": False
    }


@router.get("/telemetry/calibrate_neutral/status", response_model=NeutralCalibrationStatusResponse)
def get_neutral_affect_calibration_status_endpoint(user_id: str = Query(...)):
    """Returns neutral calibration status for a user."""
    uid = user_id.strip()
    engine = get_affect_engine(uid)
    return {
        "user_id": uid,
        "is_calibrated": engine.calibrator.is_calibrated,
        "duration_sec": engine.calibrator.calibration_duration_sec,
        "samples_buffered": len(engine.calibrator.calibration_buffer)
    }


# ============================================================================
# 4. REAL-TIME FRAME TELEMETRY STREAMING (1-2 FPS)
# ============================================================================

@router.post("/telemetry", response_model=TelemetryResponse)
async def process_telemetry_frame_endpoint(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    detector: str = Form(DEFAULT_DETECTOR),
    include_self_test: bool = Form(False)
):
    """
    Computes real-time continuous Valence-Arousal affect, Russell Circumplex quadrant,
    FACS Action Units, focal attention score, and logs biometric pulse directly to SQLite.
    """
    uid = user_id.strip()
    contents = await file.read()
    try:
        img = decode_image(contents)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        telemetry_data = await asyncio.to_thread(
            analyze_stress_and_emotion,
            img,
            detector=detector,
            user_id=uid,
            include_self_test=include_self_test
        )

        record_id = log_telemetry_live(
            user_id=uid,
            stress_score=telemetry_data.get("stress_score", 0.0),
            emotion=telemetry_data.get("dominant_emotion", "neutral"),
            status=telemetry_data.get("status", "Normal"),
            calibrated_mood=telemetry_data.get("calibrated_mood"),
            age=telemetry_data.get("age"),
            gender=telemetry_data.get("gender"),
            gender_confidence=telemetry_data.get("gender_confidence"),
            race=telemetry_data.get("race"),
            race_confidence=telemetry_data.get("race_confidence"),
            emotions_json=json.dumps(telemetry_data.get("emotions", {})),
            pitch=telemetry_data.get("pitch"),
            yaw=telemetry_data.get("yaw"),
            roll=telemetry_data.get("roll"),
            gaze_direction=telemetry_data.get("gaze_direction"),
            attention_score=telemetry_data.get("attention_score"),
            attention_status=telemetry_data.get("attention_status"),
            valence=telemetry_data.get("continuous_valence"),
            arousal=telemetry_data.get("continuous_arousal"),
            stress_classification=telemetry_data.get("stress_classification"),
            affect_quadrant=telemetry_data.get("affect_quadrant"),
            action_units_json=json.dumps(telemetry_data.get("action_units", {})),
            is_neutral_calibrated=telemetry_data.get("is_neutral_calibrated")
        )

        telemetry_data["record_id"] = record_id
        telemetry_data["user_id"] = uid
        return telemetry_data
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/telemetry", response_model=TelemetryHistoryResponse)
def get_all_telemetry_records(limit: int = 50):
    """Retrieves the latest biometric telemetry readings from SQLite."""
    return {"telemetry": get_telemetry_history(limit=limit)}


@router.get("/telemetry/{user_id}", response_model=TelemetryHistoryResponse)
def get_user_telemetry_records(user_id: str, limit: int = 50):
    """Retrieves telemetry readings for a specific user from SQLite."""
    return {
        "user_id": user_id,
        "telemetry": get_telemetry_history(user_id=user_id, limit=limit)
    }


# ============================================================================
# 5. STUDENT BIOMETRIC PROFILE & EXAM PROCTORING INTEGRATION
# ============================================================================

@router.get("/student/{user_id}/status", response_model=StudentBiometricProfileStatus)
def get_student_biometrics_status(user_id: str):
    """Returns complete biometric enrollment & calibration status for student proctoring."""
    uid = user_id.strip()
    profile = get_student_profile(uid)
    enrolled = profile.get("is_enrolled", False) or (get_face_embedding(uid) is not None)
    gaze_calib = profile.get("is_gaze_calibrated", False) or get_user_calibrator(uid).is_calibrated
    neutral_calib = profile.get("is_neutral_calibrated", False) or get_affect_engine(uid).calibrator.is_calibrated

    return {
        "user_id": uid,
        "face_enrolled": enrolled,
        "gaze_calibrated": gaze_calib,
        "neutral_calibrated": neutral_calib,
        "ready_for_exam": bool(enrolled and (gaze_calib or neutral_calib)),
        "last_updated": profile.get("enrolled_at") or profile.get("gaze_calibrated_at") or datetime.utcnow().isoformat()
    }


@router.post("/exam/{session_id}/distraction", response_model=ExamDistractionLogResponse)
def log_exam_distraction(session_id: str, payload: ExamDistractionLogRequest):
    """
    Logs an on-screen distraction event during an active exam session.
    Invoked by frontend when student looks away for >= 2 seconds.
    """
    sid = session_id.strip()
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": payload.user_id,
        "attention_score": payload.attention_score,
        "gaze_direction": payload.gaze_direction,
        "dominant_emotion": payload.dominant_emotion,
        "stress_score": payload.stress_score,
        "details": payload.details or {}
    }
    if sid not in EXAM_DISTRACTIONS:
        EXAM_DISTRACTIONS[sid] = []
    EXAM_DISTRACTIONS[sid].append(event)

    return {
        "status": "recorded",
        "session_id": sid,
        "total_distractions": len(EXAM_DISTRACTIONS[sid]),
        "event": event
    }


@router.get("/exam/{session_id}/distractions")
def get_exam_distractions(session_id: str):
    """Returns all distraction events recorded for an exam session."""
    sid = session_id.strip()
    return {
        "session_id": sid,
        "total_distractions": len(EXAM_DISTRACTIONS.get(sid, [])),
        "events": EXAM_DISTRACTIONS.get(sid, [])
    }
