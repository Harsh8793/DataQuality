"""Custom application exceptions.

Every domain error inherits from :class:`AppException` so the global handler
can translate it into a consistent API envelope with the correct HTTP status.
Internal stack traces are never exposed to clients.
"""

from __future__ import annotations

from http import HTTPStatus


class AppException(Exception):
    """Base class for all handled application exceptions."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class BadRequestException(AppException):
    """The request was malformed or semantically invalid."""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "bad_request"


class ValidationException(AppException):
    """Input failed validation rules."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class NotFoundException(AppException):
    """A requested resource does not exist."""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"


class DatasetNotFoundException(NotFoundException):
    """The requested dataset does not exist or is not owned by the caller."""

    error_code = "dataset_not_found"


class ConflictException(AppException):
    """The request conflicts with existing state (e.g. duplicate email)."""

    status_code = HTTPStatus.CONFLICT
    error_code = "conflict"


class UnauthorizedException(AppException):
    """Authentication is missing or invalid."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "unauthorized"


class UnsupportedFormatException(BadRequestException):
    """The uploaded file format/extension is not supported."""

    error_code = "unsupported_format"


class LLMException(AppException):
    """An error occurred while calling the LLM provider."""

    status_code = HTTPStatus.BAD_GATEWAY
    error_code = "llm_error"
