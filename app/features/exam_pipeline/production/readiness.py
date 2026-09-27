from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, bool]
    warnings: list[str]


def check_readiness() -> ReadinessReport:
    debug = os.getenv("FRAMEWORK_DEBUG", "false").lower() == "true"
    cors = [x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if x.strip()]
    persistence = os.getenv("PERSISTENCE_PROVIDER", "memory").strip().lower()
    db_url = os.getenv("DATABASE_URL", "").strip()
    llm_url = os.getenv("LLM_BASE_URL", "").strip()
    checks = {
        "debug_disabled": not debug,
        "cors_explicit": bool(cors),
        "durable_persistence_configured": persistence not in {"", "memory", "in_memory"} and bool(db_url),
        "llm_endpoint_configured": bool(llm_url),
        "auth_token_ttl_configured": int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800")) > 0,
    }
    warnings=[]
    if not checks["durable_persistence_configured"]:
        warnings.append("Durable persistence is not configured; current repository is in-memory and not suitable for multi-worker production deployment.")
    if not checks["cors_explicit"]:
        warnings.append("CORS_ALLOWED_ORIGINS is not explicitly configured.")
    if debug:
        warnings.append("FRAMEWORK_DEBUG is enabled.")
    return ReadinessReport(ready=all(checks.values()), checks=checks, warnings=warnings)
