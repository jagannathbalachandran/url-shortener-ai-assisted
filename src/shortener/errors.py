"""Standard JSON error shape and exception-to-response mapping.

Every error response has the shape `{"error": {"code", "message", "details"?}}`.
`details` (when present) carries only field location and message for
validation errors -- never the submitted input.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import TypedDict, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from shortener.exceptions import (
    DatabaseUnavailableError,
    InvalidExpiryError,
    InvalidUrlError,
    LinkCreationExhaustedError,
    LinkExpiredError,
    LinkNotFoundError,
    RateLimitExceededError,
)

ERROR_VALIDATION = "validation_error"
ERROR_INVALID_URL = "invalid_url"
ERROR_INVALID_EXPIRY = "invalid_expiry"
ERROR_NOT_FOUND = "not_found"
ERROR_LINK_EXPIRED = "link_expired"
ERROR_METHOD_NOT_ALLOWED = "method_not_allowed"
ERROR_HTTP_GENERIC = "http_error"
ERROR_CODE_SPACE_EXHAUSTED = "code_space_exhausted"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_NOT_READY = "not_ready"
ERROR_INTERNAL = "internal_error"

_GENERIC_INTERNAL_MESSAGE = "An unexpected error occurred."
_NOT_READY_MESSAGE = "Service is not ready."
_CODE_SPACE_EXHAUSTED_MESSAGE = "Unable to generate a unique code, please try again."
_LINK_NOT_FOUND_MESSAGE = "No link found for the given code."
_LINK_EXPIRED_MESSAGE = "This link has expired."
_RATE_LIMITED_MESSAGE = "Rate limit exceeded."
_VALIDATION_FAILED_MESSAGE = "Request validation failed."
_INVALID_URL_MESSAGE = "Invalid URL."
_INVALID_EXPIRY_MESSAGE = (
    "Invalid expires_at: must be an ISO 8601 datetime with a time zone, "
    "strictly in the future."
)
_RETRY_AFTER_HEADER = "Retry-After"
_CACHE_CONTROL_HEADER = "Cache-Control"
_NO_STORE = "no-store"

_logger = logging.getLogger(__name__)


class ErrorDetail(TypedDict):
    """One validation failure: where it occurred and why, never the input."""

    loc: list[str]
    msg: str


def build_error_body(
    code: str, message: str, details: list[ErrorDetail] | None = None
) -> dict[str, object]:
    """Assemble the standard `{"error": {...}}` response body."""
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build the standard JSON error response for one error case."""
    return JSONResponse(
        status_code=status_code,
        content=build_error_body(code, message, details),
        headers=dict(headers) if headers else None,
    )


def _handle_invalid_url_error(request: Request, exc: Exception) -> JSONResponse:
    """Map InvalidUrlError to a 422 response."""
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, ERROR_INVALID_URL, _INVALID_URL_MESSAGE
    )


def _handle_link_not_found_error(request: Request, exc: Exception) -> JSONResponse:
    """Map LinkNotFoundError to a 404 response."""
    return error_response(
        status.HTTP_404_NOT_FOUND, ERROR_NOT_FOUND, _LINK_NOT_FOUND_MESSAGE
    )


def _handle_link_expired_error(request: Request, exc: Exception) -> JSONResponse:
    """Map LinkExpiredError to a 410 response that is never cached (ADR-002 D3)."""
    return error_response(
        status.HTTP_410_GONE,
        ERROR_LINK_EXPIRED,
        _LINK_EXPIRED_MESSAGE,
        headers={_CACHE_CONTROL_HEADER: _NO_STORE},
    )


def _handle_invalid_expiry_error(request: Request, exc: Exception) -> JSONResponse:
    """Map InvalidExpiryError to a 422 response."""
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ERROR_INVALID_EXPIRY,
        _INVALID_EXPIRY_MESSAGE,
    )


def _handle_link_creation_exhausted_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """Map LinkCreationExhaustedError to a 503 response."""
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        ERROR_CODE_SPACE_EXHAUSTED,
        _CODE_SPACE_EXHAUSTED_MESSAGE,
    )


def _handle_rate_limit_exceeded_error(request: Request, exc: Exception) -> JSONResponse:
    """Map RateLimitExceededError to a 429 response with a Retry-After header."""
    rate_limit_exc = cast(RateLimitExceededError, exc)
    retry_after = str(math.ceil(rate_limit_exc.retry_after_seconds))
    return error_response(
        status.HTTP_429_TOO_MANY_REQUESTS,
        ERROR_RATE_LIMITED,
        _RATE_LIMITED_MESSAGE,
        headers={_RETRY_AFTER_HEADER: retry_after},
    )


def _handle_database_unavailable_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """Map DatabaseUnavailableError to a 503 response."""
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE, ERROR_NOT_READY, _NOT_READY_MESSAGE
    )


def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """Map Starlette's HTTPException (unmatched routes, wrong methods, ...)."""
    http_exc = cast(HTTPException, exc)
    if http_exc.status_code == status.HTTP_404_NOT_FOUND:
        code = ERROR_NOT_FOUND
    elif http_exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        code = ERROR_METHOD_NOT_ALLOWED
    else:
        code = ERROR_HTTP_GENERIC
    return error_response(
        http_exc.status_code, code, str(http_exc.detail), headers=http_exc.headers
    )


def _validation_details(exc: RequestValidationError) -> list[ErrorDetail]:
    """Extract field location and message only, never the submitted input."""
    return [
        {"loc": [str(part) for part in error["loc"]], "msg": error["msg"]}
        for error in exc.errors()
    ]


def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Map FastAPI's request validation error to a 422 response."""
    validation_exc = cast(RequestValidationError, exc)
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ERROR_VALIDATION,
        _VALIDATION_FAILED_MESSAGE,
        details=_validation_details(validation_exc),
    )


def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Map any other exception to a generic 500; log the traceback server-side."""
    # request.url.path only: no query string, no host/client, no request body.
    _logger.error(
        "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
    )
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, ERROR_INTERNAL, _GENERIC_INTERNAL_MESSAGE
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every domain and framework exception to its standard-shape handler."""
    app.add_exception_handler(InvalidUrlError, _handle_invalid_url_error)
    app.add_exception_handler(InvalidExpiryError, _handle_invalid_expiry_error)
    app.add_exception_handler(LinkNotFoundError, _handle_link_not_found_error)
    app.add_exception_handler(LinkExpiredError, _handle_link_expired_error)
    app.add_exception_handler(
        LinkCreationExhaustedError, _handle_link_creation_exhausted_error
    )
    app.add_exception_handler(RateLimitExceededError, _handle_rate_limit_exceeded_error)
    app.add_exception_handler(
        DatabaseUnavailableError, _handle_database_unavailable_error
    )
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unhandled_exception)
