"""
Vector Database Abstraction & Persistent Storage for Biometric Profiles.
Persists enrolled face vectors and calibration statuses to disk and memory.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from .config import PROFILES_STORE_FILE

# In-memory vector store dictionary
VECTOR_DATABASE: Dict[str, List[float]] = {}
STUDENT_PROFILES: Dict[str, Dict[str, Any]] = {}


def _load_persisted_profiles():
    global VECTOR_DATABASE, STUDENT_PROFILES
    try:
        path = Path(PROFILES_STORE_FILE)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                VECTOR_DATABASE = data.get("vectors", {})
                STUDENT_PROFILES = data.get("profiles", {})
    except Exception as e:
        print(f"[biometrics-db] Warning: Failed to load persisted profiles: {e}")


def _save_persisted_profiles():
    try:
        path = Path(PROFILES_STORE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "vectors": VECTOR_DATABASE,
                "profiles": STUDENT_PROFILES
            }, f, indent=2)
    except Exception as e:
        print(f"[biometrics-db] Warning: Failed to save profiles to disk: {e}")


# Initialize from disk
_load_persisted_profiles()


def save_face_embedding(user_id: str, embedding: List[float]) -> None:
    """Stores or updates the 512-D ArcFace embedding for an enrolled user."""
    uid = user_id.strip()
    VECTOR_DATABASE[uid] = embedding
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {}
    STUDENT_PROFILES[uid]["is_enrolled"] = True
    _save_persisted_profiles()


def get_face_embedding(user_id: str) -> Optional[List[float]]:
    """Retrieves the 512-D embedding for a user if enrolled, else None."""
    return VECTOR_DATABASE.get(user_id.strip())


def delete_face_embedding(user_id: str) -> bool:
    """Deletes an enrolled user. Returns True if deleted, False if not found."""
    uid = user_id.strip()
    if uid in VECTOR_DATABASE:
        del VECTOR_DATABASE[uid]
        if uid in STUDENT_PROFILES:
            STUDENT_PROFILES[uid]["is_enrolled"] = False
        _save_persisted_profiles()
        return True
    return False


def list_enrolled_users() -> List[str]:
    """Returns a list of all currently enrolled user identifiers."""
    return list(VECTOR_DATABASE.keys())


def get_enrolled_count() -> int:
    """Returns the total number of enrolled users in the database."""
    return len(VECTOR_DATABASE)


def update_student_profile(user_id: str, updates: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """Updates student calibration flags (gaze, neutral, etc.)."""
    uid = user_id.strip()
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {
            "is_enrolled": uid in VECTOR_DATABASE,
            "is_gaze_calibrated": False,
            "is_neutral_calibrated": False
        }
    if updates:
        STUDENT_PROFILES[uid].update(updates)
    if kwargs:
        STUDENT_PROFILES[uid].update(kwargs)
    _save_persisted_profiles()
    return STUDENT_PROFILES[uid]


def get_student_profile(user_id: str) -> Dict[str, Any]:
    """Returns the complete biometric profile status for a student."""
    uid = user_id.strip()
    profile = STUDENT_PROFILES.get(uid, {
        "is_enrolled": uid in VECTOR_DATABASE,
        "is_gaze_calibrated": False,
        "is_neutral_calibrated": False
    })
    profile["is_enrolled"] = uid in VECTOR_DATABASE
    return profile
