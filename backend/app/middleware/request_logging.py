"""Request logging middleware: assigns a request id and logs timing."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger("api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request's method, path, status and execution time (ms)."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        request.state.request_id = request_id

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.1f ms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response
