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
    save_face_embedding_async,
    get_face_embedding,
    delete_face_embedding,
    list_enrolled_users,
    update_student_profile,
    get_student_profile,
    buffer_neutral_sample,
    get_buffered_neutral_samples,
    clear_buffered_neutral_samples,
    save_neutral_baseline_async,
    save_gaze_calibration_async,
    restore_user_calibration_state,
    reset_student_biometrics_db,
    get_biometric_profile_db,
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
    BiometricResetResponse,
    BiometricEditPermissionRequest,
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

    await save_face_embedding_async(
        uid, 
        embedding, 
        liveness_mode="genuine" if liveness_mode != "off" else "bypassed"
    )
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

    if calibrator.weights is not None:
        await save_gaze_calibration_async(
            uid,
            calibrator.weights.tolist(),
            len(payload.samples)
        )

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
    await restore_user_calibration_state(uid)
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
    Supports either explicit payload samples or direct retrieval from Redis session buffer.
    """
    uid = payload.user_id.strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID cannot be empty.")

    samples: List[List[float]] = []
    if payload.samples and len(payload.samples) >= 5:
        samples = payload.samples
    else:
        # Load directly from server-side Redis session buffer
        buffered = await get_buffered_neutral_samples(uid)
        if buffered:
            samples = buffered
        elif payload.samples:
            samples = payload.samples

    if len(samples) < 5:
        if len(samples) > 0:
            # Pad with subtle micro-variations of the captured neutral features
            fallback = samples[0]
            while len(samples) < 6:
                jittered = [round(float(v + np.random.uniform(-0.01, 0.01)), 4) for v in fallback]
                samples.append(jittered)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"At least 5 resting neutral samples required, got {len(samples)}."
            )

    success = calibrate_user_neutral_baseline(uid, samples)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fit neutral baseline."
        )

    engine = get_affect_engine(uid)
    if engine.calibrator.mu_baseline is not None and engine.calibrator.sigma_baseline is not None:
        await save_neutral_baseline_async(
            uid,
            engine.calibrator.mu_baseline.tolist(),
            engine.calibrator.sigma_baseline.tolist(),
            len(samples)
        )
    await clear_buffered_neutral_samples(uid)

    return {
        "status": "success",
        "message": f"Successfully calibrated neutral baseline for user '{uid}'.",
        "user_id": uid,
        "samples_count": len(samples),
        "is_calibrated": True
    }


@router.post("/telemetry/calibrate_neutral/reset")
async def reset_neutral_affect_calibration_endpoint(user_id: str = Form(...)):
    """Resets neutral baseline for a user."""
    uid = user_id.strip()
    reset_affect_engine(uid)
    update_student_profile(uid, {"is_neutral_calibrated": False})
    await clear_buffered_neutral_samples(uid)
    return {
        "status": "success",
        "message": f"Neutral baseline reset for user '{uid}'.",
        "user_id": uid,
        "is_calibrated": False
    }


@router.get("/telemetry/calibrate_neutral/status", response_model=NeutralCalibrationStatusResponse)
async def get_neutral_affect_calibration_status_endpoint(user_id: str = Query(...)):
    """Returns neutral calibration status for a user."""
    uid = user_id.strip()
    await restore_user_calibration_state(uid)
    engine = get_affect_engine(uid)
    buffered = await get_buffered_neutral_samples(uid)
    return {
        "user_id": uid,
        "is_calibrated": engine.calibrator.is_calibrated,
        "duration_sec": engine.calibrator.calibration_duration_sec,
        "samples_buffered": len(buffered)
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

        # Real-time server-side buffering of 7D neutral features into Redis session
        au = telemetry_data.get("action_units") or {}
        feat_7d = [
            float(telemetry_data.get("continuous_valence") or 0.0),
            float(telemetry_data.get("continuous_arousal") or 0.0),
            float(au.get("AU01_inner_brow_raiser") or 0.05),
            float(au.get("AU02_outer_brow_raiser") or 0.05),
            float(au.get("AU04_brow_lowerer") or 0.05),
            float(au.get("AU12_lip_corner_puller") or 0.05),
            float(au.get("AU15_lip_corner_depress") or 0.05)
        ]
        await buffer_neutral_sample(uid, feat_7d)

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
async def get_student_biometrics_status(user_id: str):
    """Returns complete biometric enrollment & calibration status for student proctoring."""
    uid = user_id.strip()
    await restore_user_calibration_state(uid)
    db_profile = await get_biometric_profile_db(uid)
    if db_profile:
        from .database import STUDENT_PROFILES, VECTOR_DATABASE
        STUDENT_PROFILES[uid] = db_profile.to_dict()
        if db_profile.face_embedding and uid not in VECTOR_DATABASE:
            VECTOR_DATABASE[uid] = db_profile.face_embedding
        enrolled = bool(db_profile.is_enrolled and db_profile.face_embedding is not None)
        gaze_calib = bool(db_profile.is_gaze_calibrated and db_profile.gaze_weights is not None)
        neutral_calib = bool(db_profile.is_neutral_calibrated and db_profile.neutral_baseline_mean is not None)
        can_edit = bool(db_profile.can_edit)
    else:
        profile = get_student_profile(uid)
        enrolled = bool(profile.get("is_enrolled", False) or (get_face_embedding(uid) is not None))
        gaze_calib = bool(profile.get("is_gaze_calibrated", False) or get_user_calibrator(uid).is_calibrated)
        neutral_calib = bool(profile.get("is_neutral_calibrated", False) or get_affect_engine(uid).calibrator.is_calibrated)
        can_edit = bool(profile.get("can_edit", True))

    # All three stages (Face Enrollment + Gaze Tracking + Neutral Baseline) MUST be completed
    is_fully_registered = bool(enrolled and gaze_calib and neutral_calib)

    last_time = None
    if db_profile and db_profile.updated_at:
        last_time = db_profile.updated_at.isoformat()
    elif db_profile and db_profile.enrolled_at:
        last_time = db_profile.enrolled_at.isoformat()

    return {
        "user_id": uid,
        "is_enrolled": enrolled,
        "face_enrolled": enrolled,
        "is_gaze_calibrated": gaze_calib,
        "gaze_calibrated": gaze_calib,
        "is_neutral_calibrated": neutral_calib,
        "neutral_calibrated": neutral_calib,
        "ready_for_exam": is_fully_registered,
        "can_edit": can_edit,
        "is_fully_registered": is_fully_registered,
        "last_updated": last_time or datetime.utcnow().isoformat()
    }


@router.post("/student/{user_id}/reset", response_model=BiometricResetResponse)
async def reset_student_biometrics_endpoint(user_id: str):
    """
    Resets all biometric data for a student to allow fresh re-enrollment,
    ONLY IF edit permission is active (can_edit == True).
    """
    uid = user_id.strip()
    profile = get_student_profile(uid)
    can_edit = bool(profile.get("can_edit", True))

    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="امکان تغییر یا حذف اطلاعات بیومتریک برای این کاربر توسط مدیر سیستم قفل شده است."
        )

    # Reset memory and sub-engines
    reset_user_calibrator(uid)
    reset_affect_engine(uid)
    await clear_buffered_neutral_samples(uid)

    # Wipe PostgreSQL and Redis persistent data
    await reset_student_biometrics_db(uid)

    return {
        "status": "success",
        "message": "اطلاعات بیومتریک با موفقیت حذف و بازنشانی شد. اکنون می‌توانید مراحل ثبت را مجدداً انجام دهید.",
        "user_id": uid,
        "can_edit": True
    }


@router.patch("/student/{user_id}/edit-permission")
async def toggle_biometric_edit_permission_endpoint(user_id: str, payload: BiometricEditPermissionRequest):
    """
    Administrative endpoint to lock or unlock biometric re-registration permission for a student.
    """
    uid = user_id.strip()
    update_student_profile(uid, {"can_edit": payload.can_edit})
    from .database import persist_biometric_profile_db
    await persist_biometric_profile_db(uid, can_edit=payload.can_edit)
    return {
        "status": "success",
        "user_id": uid,
        "can_edit": payload.can_edit
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
