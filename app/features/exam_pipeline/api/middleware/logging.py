"""
HTTP request logging middleware.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

from ...logging import logger
class LoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request,
        call_next,
    ):

        logger.info(

            "HTTP request",

            method=request.method,

            path=request.url.path,

        )

        response = await call_next(request)

        logger.info(

            "HTTP response",

            method=request.method,

            path=request.url.path,

            status=response.status_code,

        )

        return response