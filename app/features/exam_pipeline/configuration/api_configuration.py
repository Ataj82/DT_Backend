from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class APIConfiguration:

    title: str = "Assessment Framework"

    version: str = "1.0.0"

    docs_url: str = "/docs"

    redoc_url: str = "/redoc"

    openapi_url: str = "/openapi.json"