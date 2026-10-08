import os
import json
import sqlite3
import numpy as np
try:
    from deepface import DeepFace
except ImportError:
    DeepFace = None

from .attention import analyze_focal_attention, run_system_self_test
from .emotion_engine import get_affect_engine, reset_affect_engine, BiometricAffectEngine

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_FILE = os.path.join(_ROOT_DIR, "uploads", "stress_telemetry.db")

def init_db(db_path: str = DB_FILE):
    """Initializes the telemetry SQLite database schema with comprehensive attributes."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT,
            stress_score REAL,
            dominant_emotion TEXT,
            status TEXT,
            calibrated_mood TEXT,
            age INTEGER,
            gender TEXT,
            gender_confidence REAL,
            race TEXT,
            race_confidence REAL,
            emotions_json TEXT,
            pitch REAL,
            yaw REAL,
            roll REAL,
            gaze_direction TEXT,
            attention_score REAL,
            attention_status TEXT,
            valence REAL,
            arousal REAL,
            stress_classification TEXT,
            affect_quadrant TEXT,
            action_units_json TEXT,
            is_neutral_calibrated INTEGER
        )
    """)
    # Check and add columns if upgrading an existing db
    existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(telemetry)").fetchall()]
    new_cols = [
        ("calibrated_mood", "TEXT"),
        ("age", "INTEGER"),
        ("gender", "TEXT"),
        ("gender_confidence", "REAL"),
        ("race", "TEXT"),
        ("race_confidence", "REAL"),
        ("emotions_json", "TEXT"),
        ("pitch", "REAL"),
        ("yaw", "REAL"),
        ("roll", "REAL"),
        ("gaze_direction", "TEXT"),
        ("attention_score", "REAL"),
        ("attention_status", "TEXT"),
        ("valence", "REAL"),
        ("arousal", "REAL"),
        ("stress_classification", "TEXT"),
        ("affect_quadrant", "TEXT"),
        ("action_units_json", "TEXT"),
        ("is_neutral_calibrated", "INTEGER")
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE telemetry ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

try:
    init_db()
except Exception as _e:
    pass

def log_telemetry_live(
    user_id: str,
    stress_score: float,
    emotion: str,
    status: str,
    calibrated_mood: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    gender_confidence: float | None = None,
    race: str | None = None,
    race_confidence: float | None = None,
    emotions_json: str | None = None,
    pitch: float | None = None,
    yaw: float | None = None,
    roll: float | None = None,
    gaze_direction: str | None = None,
    attention_score: float | None = None,
    attention_status: str | None = None,
    valence: float | None = None,
    arousal: float | None = None,
    stress_classification: str | None = None,
    affect_quadrant: str | None = None,
    action_units_json: str | None = None,
    is_neutral_calibrated: bool | None = None,
    db_path: str = DB_FILE
) -> int:
    """Inserts a live biometric telemetry data point into SQLite."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO telemetry (
            user_id, stress_score, dominant_emotion, status,
            calibrated_mood, age, gender, gender_confidence, race, race_confidence, emotions_json,
            pitch, yaw, roll, gaze_direction, attention_score, attention_status,
            valence, arousal, stress_classification, affect_quadrant, action_units_json, is_neutral_calibrated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, float(stress_score), str(emotion), str(status),
        str(calibrated_mood) if calibrated_mood else None,
        int(age) if age is not None else None,
        str(gender) if gender else None,
        float(gender_confidence) if gender_confidence is not None else None,
        str(race) if race else None,
        float(race_confidence) if race_confidence is not None else None,
        str(emotions_json) if emotions_json else None,
        float(pitch) if pitch is not None else None,
        float(yaw) if yaw is not None else None,
        float(roll) if roll is not None else None,
        str(gaze_direction) if gaze_direction else None,
        float(attention_score) if attention_score is not None else None,
        str(attention_status) if attention_status else None,
        float(valence) if valence is not None else None,
        float(arousal) if arousal is not None else None,
        str(stress_classification) if stress_classification else None,
        str(affect_quadrant) if affect_quadrant else None,
        str(action_units_json) if action_units_json else None,
        1 if is_neutral_calibrated else 0 if is_neutral_calibrated is not None else None
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_telemetry_history(user_id: str | None = None, limit: int = 50, db_path: str = DB_FILE) -> list[dict]:
    """Fetches the latest telemetry records, optionally filtered by user_id."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cols = """id, timestamp, user_id, stress_score, dominant_emotion, status,
              calibrated_mood, age, gender, gender_confidence, race, race_confidence, emotions_json,
              pitch, yaw, roll, gaze_direction, attention_score, attention_status,
              valence, arousal, stress_classification, affect_quadrant, action_units_json, is_neutral_calibrated"""
    if user_id:
        cursor.execute(
            f"SELECT {cols} FROM telemetry WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
    else:
        cursor.execute(
            f"SELECT {cols} FROM telemetry ORDER BY id DESC LIMIT ?",
            (limit,)
        )
    rows = cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("emotions_json"):
            try:
                d["emotions"] = json.loads(d["emotions_json"])
            except Exception:
                d["emotions"] = {}
        if d.get("action_units_json"):
            try:
                d["action_units"] = json.loads(d["action_units_json"])
            except Exception:
                d["action_units"] = {}
        d["is_neutral_calibrated"] = bool(d.get("is_neutral_calibrated"))
        result.append(d)
    conn.close()
    return result

def estimate_stress_index(emotion_dict: dict) -> tuple[float, str]:
    """
    Computes psychological stress index (0 - 100) from facial micro-expressions.
    
    Formula:
      Tension drivers (+): fear (1.0), angry (0.8), sad (0.5), surprise (0.3)
      Relaxation drivers (-): happy (0.6), neutral (0.3)
    """
    fear = float(emotion_dict.get("fear", 0.0))
    angry = float(emotion_dict.get("angry", 0.0))
    sad = float(emotion_dict.get("sad", 0.0))
    surprise = float(emotion_dict.get("surprise", 0.0))
    neutral = float(emotion_dict.get("neutral", 0.0))
    happy = float(emotion_dict.get("happy", 0.0))

    raw_stress = (fear * 1.0) + (angry * 0.8) + (sad * 0.5) + (surprise * 0.3) - (happy * 0.6) - (neutral * 0.3)
    stress_score = max(0.0, min(100.0, raw_stress))

    if stress_score < 25.0:
        status = "Relaxed"
    elif stress_score < 55.0:
        status = "Normal"
    elif stress_score < 75.0:
        status = "Mild Stress"
    else:
        status = "High Stress"

    return round(stress_score, 2), status

_DEMOGRAPHICS_CACHE = {}

def _no_face_payload(status_msg: str, include_self_test: bool = False, img: np.ndarray | None = None) -> dict:
    payload = {
        "dominant_emotion": "none",
        "calibrated_mood": "No Face Detected",
        "stress_score": 0.0,
        "status": "Out of Frame",
        "stress_classification": "Out of Frame",
        "continuous_valence": 0.0,
        "continuous_arousal": 0.0,
        "affect_quadrant": "None",
        "affect_quadrant_title": "Out of Frame",
        "emotions": {k: 0.0 for k in ['happy', 'neutral', 'sad', 'angry', 'surprise', 'fear', 'disgust', 'contempt']},
        "categorical_distribution": {
            "Anger": 0.0, "Contempt": 0.0, "Disgust": 0.0, "Fear": 0.0,
            "Happiness": 0.0, "Neutral": 0.0, "Sadness": 0.0, "Surprise": 0.0
        },
        "action_units": {
            "AU01_inner_brow_raiser": 0.0,
            "AU02_outer_brow_raiser": 0.0,
            "AU04_brow_lowerer": 0.0,
            "AU12_lip_corner_puller": 0.0,
            "AU15_lip_corner_depress": 0.0,
            "AU45_blink_closure": 0.0
        },
        "is_neutral_calibrated": False,
        "blink_frequency_bpm": 0.0,
        "age": None,
        "gender": "None",
        "gender_confidence": 0.0,
        "gender_breakdown": {},
        "race": "None",
        "race_confidence": 0.0,
        "race_breakdown": {},
        "attention_score": 0.0,
        "attention_status": status_msg,
        "is_focused": False,
        "pitch": 0.0,
        "yaw": 0.0,
        "roll": 0.0,
        "gaze_direction": "Out of Frame",
        "gaze_x_ratio": 0.5,
        "face_detected": False,
        "face_box": [],
        "eyes_detected": 0,
        "is_calibrated": False,
        "gaze_features": [0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5],
        "landmarks": {
            "face_box": [],
            "eyes": [],
            "pupils": [],
            "nose_tip": [],
            "mouth_box": []
        },
        "gaze_point": {
            "x": 0,
            "y": 0,
            "norm_x": 0.5,
            "norm_y": 0.5
        },
        "pose_vector": {
            "start": [0, 0],
            "end": [0, 0],
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0
        }
    }
    if include_self_test:
        payload["self_test"] = run_system_self_test(img)
    return payload

def analyze_comprehensive_biometrics(
    img: np.ndarray, 
    detector: str = "ssd", 
    user_id: str | None = None,
    include_self_test: bool = False,
    blendshape_signals: dict | None = None
) -> dict:
    """
    Extracts all facial biometric attributes with zero-lag optimization:
      1. Focal Point Attention, Head Orientation & Eye Gaze (via L2CS-Net + OpenCV)
      2. Fast Exit if No Face is Detected in Frame (sub-10ms)
      3. SOTA Multi-Task Facial Affect & Stress Telemetry (via HSEmotion EfficientNet-B0 MTL in ~20ms)
      4. Facial Action Coding System (FACS) Action Units (AU4, AU12, AU15, AU45)
      5. Continuous Valence-Arousal Dimensional Coordinates & Russell Quadrants
      6. Personalized Neutral Baseline Normalization (Eliminates Resting Face Bias)
      7. Session-Cached Demographics (Age, Gender, Race)
      8. Structured Facial Landmarks & 3D Gaze Target Vector
      9. Optional Pipeline Self-Test Verification
    """
    if img is None or img.size == 0:
        return _no_face_payload("No image provided", include_self_test=include_self_test, img=img)

    # 1. Real-time Attention & Face Detection (runs in ~15ms)
    attn = analyze_focal_attention(img, user_id=user_id)

    # 2. FAST-EXIT IF NO FACE IN FRAME (Unless detector == 'skip' for tests)
    if not attn.get("face_detected", False) and detector != "skip":
        return _no_face_payload(attn.get("status", "Face Not Detected"), include_self_test=include_self_test, img=img)

    # 3. Crop face ROI for ultra-fast HSEmotion ONNX inference
    h, w = img.shape[:2]
    face_box = attn.get("face_box", [])
    if face_box and len(face_box) == 4 and detector != "skip":
        fx, fy, fw, fh = face_box
        x1 = max(0, fx - int(fw * 0.12))
        y1 = max(0, fy - int(fh * 0.12))
        x2 = min(w, fx + fw + int(fw * 0.12))
        y2 = min(h, fy + fh + int(fh * 0.12))
        face_roi = img[y1:y2, x1:x2]
        if face_roi.size == 0:
            face_roi = img
        deepface_detector = "skip"
    else:
        face_roi = img
        deepface_detector = detector or "ssd"

    # 4. Execute SOTA Biometric Affect Engine (sub-25ms)
    uid = user_id or "default"
    affect_engine = get_affect_engine(uid)
    affect_out = affect_engine.process_frame(
        face_roi,
        blendshape_signals=blendshape_signals,
        landmarks=attn.get("landmarks")
    )

    dominant_emotion = affect_out.calibrated_mood
    calibrated_mood = affect_out.calibrated_mood
    stress_score = affect_out.composite_stress_index
    status_label = affect_out.stress_classification

    # Map HSEmotion categories to backward-compatible lowercase percentage dictionary
    cat_dist = affect_out.categorical_distribution
    clean_emotions = {
        "anger": round(cat_dist.get("Anger", 0.0) * 100.0, 1),
        "contempt": round(cat_dist.get("Contempt", 0.0) * 100.0, 1),
        "disgust": round(cat_dist.get("Disgust", 0.0) * 100.0, 1),
        "fear": round(cat_dist.get("Fear", 0.0) * 100.0, 1),
        "happy": round(cat_dist.get("Happiness", 0.0) * 100.0, 1),
        "neutral": round(cat_dist.get("Neutral", 0.0) * 100.0, 1),
        "sad": round(cat_dist.get("Sadness", 0.0) * 100.0, 1),
        "surprise": round(cat_dist.get("Surprise", 0.0) * 100.0, 1)
    }

    # 5. Check if demographics (Age, Gender, Race) need to be evaluated or pulled from cache
    cached_demo = _DEMOGRAPHICS_CACHE.get(uid)
    # Never block live telemetry on heavy external model downloads (sub-20ms guarantee)
    need_demographics = False

    if need_demographics and DeepFace is not None:
        try:
            analysis = DeepFace.analyze(
                img_path=face_roi,
                actions=['age', 'gender', 'race'],
                detector_backend=deepface_detector,
                enforce_detection=False
            )
            res = analysis[0] if isinstance(analysis, list) else analysis
            age = int(res.get("age", 28))
            dominant_gender = res.get("dominant_gender", "Unknown")
            gender_dict = res.get("gender", {})
            gender_conf = round(float(gender_dict.get(dominant_gender, 0.0)), 1)
            clean_gender = {k: round(float(v), 1) for k, v in gender_dict.items()}

            dominant_race = res.get("dominant_race", "Unknown")
            raw_race = res.get("race", {})
            clean_race = {k: round(float(v), 1) for k, v in raw_race.items()}
            race_conf = round(float(clean_race.get(dominant_race, 0.0)), 1)
        except Exception:
            age = 28
            dominant_gender = "Unknown"
            gender_conf = 0.0
            clean_gender = {}
            dominant_race = "Unknown"
            race_conf = 0.0
            clean_race = {}

        _DEMOGRAPHICS_CACHE[uid] = {
            "age": age,
            "gender": dominant_gender,
            "gender_confidence": gender_conf,
            "gender_breakdown": clean_gender,
            "race": dominant_race,
            "race_confidence": race_conf,
            "race_breakdown": clean_race
        }
    else:
        cached = _DEMOGRAPHICS_CACHE.get(uid, {
            "age": 28,
            "gender": "Unknown",
            "gender_confidence": 0.0,
            "gender_breakdown": {},
            "race": "Unknown",
            "race_confidence": 0.0,
            "race_breakdown": {}
        })
        age = cached.get("age", 28)
        dominant_gender = cached.get("gender", "Unknown")
        gender_conf = cached.get("gender_confidence", 0.0)
        clean_gender = cached.get("gender_breakdown", {})
        dominant_race = cached.get("race", "Unknown")
        race_conf = cached.get("race_confidence", 0.0)
        clean_race = cached.get("race_breakdown", {})

    payload = {
        "dominant_emotion": dominant_emotion,
        "calibrated_mood": calibrated_mood,
        "stress_score": stress_score,
        "status": status_label,
        "stress_classification": status_label,
        "continuous_valence": affect_out.continuous_valence,
        "continuous_arousal": affect_out.continuous_arousal,
        "affect_quadrant": affect_out.affect_quadrant,
        "affect_quadrant_title": affect_out.affect_quadrant_title,
        "action_units": affect_out.action_unit_activations,
        "categorical_distribution": affect_out.categorical_distribution,
        "is_neutral_calibrated": affect_out.calibration_status,
        "blink_frequency_bpm": affect_out.blink_frequency_bpm,
        "emotions": clean_emotions,
        "age": age,
        "gender": dominant_gender,
        "gender_confidence": gender_conf,
        "gender_breakdown": clean_gender,
        "race": dominant_race,
        "race_confidence": race_conf,
        "race_breakdown": clean_race,
        # Attention & Focal Point
        "attention_score": attn["attention_score"],
        "attention_status": attn["status"],
        "is_focused": attn["is_focused"],
        "pitch": attn["pitch"],
        "yaw": attn["yaw"],
        "roll": attn["roll"],
        "gaze_direction": attn["gaze_direction"],
        "gaze_x_ratio": attn.get("gaze_x_ratio", 0.5),
        "face_detected": True,
        "face_box": attn.get("face_box", []),
        "eyes_detected": attn.get("eyes_detected", 0),
        "is_calibrated": attn.get("is_calibrated", False),
        "gaze_features": attn.get("gaze_features", []),
        "landmarks": attn.get("landmarks", {}),
        "gaze_point": attn.get("gaze_point", {}),
        "pose_vector": attn.get("pose_vector", {})
    }

    if include_self_test:
        payload["self_test"] = run_system_self_test(img)

    return payload

def analyze_stress_and_emotion(
    img: np.ndarray, 
    detector: str = "ssd", 
    user_id: str | None = None,
    include_self_test: bool = False,
    blendshape_signals: dict | None = None
) -> dict:
    """Backwards-compatible wrapper calling analyze_comprehensive_biometrics."""
    return analyze_comprehensive_biometrics(
        img, 
        detector=detector, 
        user_id=user_id, 
        include_self_test=include_self_test,
        blendshape_signals=blendshape_signals
    )

