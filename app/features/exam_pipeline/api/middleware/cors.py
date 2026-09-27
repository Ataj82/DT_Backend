"""CORS configuration with safe production defaults."""
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def configure_cors(app: FastAPI, origins: list[str] | None = None):
    """Configure CORS without combining wildcard origins and credentials."""
    if origins is None:
        raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
        origins = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
    if not origins:
        # Development remains usable, while production readiness explicitly
        # rejects the implicit wildcard configuration.
        origins = ["*"]
        allow_credentials = False
    else:
        allow_credentials = True
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
