"""
Biometric & Affect Telemetry Configuration for Backend.
Supports direct execution and microservice proxying.
"""

import os
from pathlib import Path

# Base directory paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Models locations (checks local features/biometrics/models, face-auth-service, or env)
DEFAULT_LOCAL_MODELS_DIR = APP_DIR / "models"
DEFAULT_FACE_SVC_MODELS_DIR = PROJECT_ROOT / "face" / "face-auth-service" / "models"

MODELS_DIR = (
    DEFAULT_LOCAL_MODELS_DIR
    if DEFAULT_LOCAL_MODELS_DIR.exists()
    else DEFAULT_FACE_SVC_MODELS_DIR
)

# ONNX Model Paths
GAZE_MODEL_PATH = os.getenv(
    "GAZE_MODEL_PATH",
    str(MODELS_DIR / "mobileone_s0_gaze.onnx")
)

EMOTION_MODEL_PATH = os.getenv(
    "EMOTION_MODEL_PATH",
    str(MODELS_DIR / "enet_b0_8_va_mtl.onnx")
)

# SQLite Telemetry Storage
DB_FILE = os.getenv(
    "BIOMETRICS_DB_FILE",
    str(PROJECT_ROOT / "face" / "face-auth-service" / "stress_telemetry.db")
)

# Persistent Biometric Profiles Storage
PROFILES_STORE_FILE = os.getenv(
    "BIOMETRIC_PROFILES_FILE",
    str(PROJECT_ROOT / "Backend" / "uploads" / "biometric_profiles.json")
)

# Biometrics Service URL (for proxying when running as microservice in Docker)
BIOMETRICS_SERVICE_URL = os.getenv(
    "BIOMETRICS_SERVICE_URL",
    "http://face_auth_api:8000"
)

# ArcFace Verification Parameters
COSINE_THRESHOLD = float(os.getenv("COSINE_THRESHOLD", "0.65"))

# Telemetry Defaults
DEFAULT_LIVENESS_MODE = os.getenv("DEFAULT_LIVENESS_MODE", "balanced")
DEFAULT_DETECTOR = os.getenv("DEFAULT_DETECTOR", "ssd")
DEFAULT_TELEMETRY_FPS = float(os.getenv("DEFAULT_TELEMETRY_FPS", "2.0"))
CPU_EXECUTION_THREADS = int(os.getenv("CPU_EXECUTION_THREADS", "4"))
