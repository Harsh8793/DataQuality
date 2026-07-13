"""Global exception handlers that translate errors into the API envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.exceptions.base import AppException
from app.schemas.common import ApiResponse, ErrorDetail

logger = get_logger(__name__)


def _envelope(message: str, code: str, status_code: int, field: str | None = None) -> JSONResponse:
    """Serialize a failed :class:`ApiResponse` to a JSON response."""
    payload = ApiResponse.fail(message=message, errors=[ErrorDetail(code=code, message=message, field=field)])
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to the FastAPI app."""

    @app.exception_handler(AppException)
    async def _handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        logger.warning("AppException [%s]: %s", exc.error_code, exc.message)
        return _envelope(exc.message, exc.error_code, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body") or None
        message = first.get("msg", "Validation error")
        logger.info("Validation error on %s: %s", field, message)
        return _envelope(message, "validation_error", 422, field)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(str(exc.detail), "http_error", exc.status_code)

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internal details to the client.
        logger.exception("Unhandled exception: %s", exc)
        return _envelope("An unexpected error occurred.", "internal_error", 500)
