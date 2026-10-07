"""
Biometric & Affect Telemetry Configuration for DT Backend.
Manages local ONNX model paths and SQLite/JSON storage directly in Backend.
"""

import os
from pathlib import Path

# Base directory paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent.parent
UPLOADS_DIR = BACKEND_DIR / "uploads"

# Local models directory
MODELS_DIR = APP_DIR / "models"

# ONNX Model Paths
GAZE_MODEL_PATH = os.getenv(
    "GAZE_MODEL_PATH",
    str(MODELS_DIR / "mobileone_s0_gaze.onnx")
)

EMOTION_MODEL_PATH = os.getenv(
    "EMOTION_MODEL_PATH",
    str(MODELS_DIR / "enet_b0_8_va_mtl.onnx")
)

# SQLite Telemetry Storage (in Backend/uploads/)
DB_FILE = os.getenv(
    "BIOMETRICS_DB_FILE",
    str(UPLOADS_DIR / "stress_telemetry.db")
)

# Persistent Biometric Profiles Storage (in Backend/uploads/)
PROFILES_STORE_FILE = os.getenv(
    "BIOMETRIC_PROFILES_FILE",
    str(UPLOADS_DIR / "biometric_profiles.json")
)

# ArcFace Verification Parameters
COSINE_THRESHOLD = float(os.getenv("COSINE_THRESHOLD", "0.65"))

# Telemetry Defaults
DEFAULT_LIVENESS_MODE = os.getenv("DEFAULT_LIVENESS_MODE", "balanced")
DEFAULT_DETECTOR = os.getenv("DEFAULT_DETECTOR", "ssd")
DEFAULT_TELEMETRY_FPS = float(os.getenv("DEFAULT_TELEMETRY_FPS", "2.0"))
CPU_EXECUTION_THREADS = int(os.getenv("CPU_EXECUTION_THREADS", "4"))
