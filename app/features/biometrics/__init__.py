"""
Biometrics feature package for DT Backend.
Integrates face authentication, gaze tracking, emotion baseline, and real-time exam proctoring.
"""

from .router import router, biometrics_router

__all__ = ["router", "biometrics_router"]
