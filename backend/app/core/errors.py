"""Standard API errors and a global exception handler."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Business/domain error carrying an HTTP status and a stable error code."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def validation_error(message: str, details: dict | None = None) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, details)


def unauthenticated(message: str = "Authentication required") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message)


def forbidden(message: str = "Forbidden") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(message: str = "Not found") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def invalid_transition(message: str, details: dict | None = None) -> ApiError:
    return ApiError(409, "INVALID_TRANSITION", message, details)


def duplicate_check_in(message: str, details: dict | None = None) -> ApiError:
    return ApiError(409, "DUPLICATE_CHECK_IN", message, details)


def cashier_busy(message: str, details: dict | None = None) -> ApiError:
    return ApiError(409, "CASHIER_BUSY", message, details)


def service_unavailable(message: str = "Service unavailable") -> ApiError:
    return ApiError(503, "SERVICE_UNAVAILABLE", message)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        # Avoid leaking internals; log is handled by uvicorn.
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )
