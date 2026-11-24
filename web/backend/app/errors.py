"""Application error types and JSON-safe error envelopes."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class InputValidationError(AppError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnavailableError(AppError):
    status_code = 503
    code = "unavailable"


class IntegrityError(AppError):
    """Raised when a broadcast model fails its integrity check."""

    status_code = 409
    code = "integrity_error"


class ResearchExecutionDisabled(UnavailableError):
    code = "research_execution_disabled"


class JobCancelled(Exception):
    """Raised by a job handler when cooperative cancellation is observed."""
