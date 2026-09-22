# app/middleware.py
import logging
import uuid
from typing import Callable, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class UserIdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        SKIP_PATHS = {"/acc/v1/docs", "/acc/v1/openapi.json", "/metrics", "/health","/acc/v1/search/products","/acc/v1/search/countries", "/acc/v1/check/limit",
                      "/acc/v1/search/customs-locations"}
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        raw = request.headers.get("X-User-ID")
        raw_type= request.headers.get("X-User-Type")
        raw_tenant = request.headers.get("X-Tenant-Id")
        if raw_tenant:
            request.state.tenant_id = raw_tenant
            
        if not raw:
            raise HTTPException(status_code=400, detail="X-User-ID header required")
        if not raw_type:
            raise HTTPException(status_code=400, detail="X-User-Type header required")

        try:
            user_id = uuid.UUID(raw)  # validate + normalize
            user_type = str(raw_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-User-ID must be a valid UUID")

        # store a UUID, not a dict or tuple
        request.state.user_id = user_id
        request.state.user_type = user_type
        return await call_next(request)
