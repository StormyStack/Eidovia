"""
Gateway Error Handling
Every non-2xx response has the shape (see docs/api-auth-home.md):

    { "detail": { "code": "...", "message": "...", "fields": { ... } } }
"""

import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error that maps directly onto the contract's error format."""

    def __init__(self, status_code: int, code: str, message: str, fields: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


# ── Convenience constructors (codes from the contract) ──

def validation_error(fields: dict, message: str = "Please fix the highlighted fields.") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, fields)


def invalid_credentials() -> ApiError:
    return ApiError(401, "INVALID_CREDENTIALS", "Incorrect username or password.")


def token_missing() -> ApiError:
    return ApiError(401, "TOKEN_MISSING", "You need to log in to continue.")


def token_invalid() -> ApiError:
    return ApiError(401, "TOKEN_INVALID", "Your session is not valid. Please log in again.")


def token_expired() -> ApiError:
    return ApiError(401, "TOKEN_EXPIRED", "Your session has expired. Please log in again.")


def forbidden() -> ApiError:
    return ApiError(403, "FORBIDDEN", "You do not have access to this resource.")


def module_not_found() -> ApiError:
    return ApiError(404, "MODULE_NOT_FOUND", "This module could not be found.")


def username_taken() -> ApiError:
    return ApiError(409, "USERNAME_TAKEN", "This username is already taken.", {"username": "This username is already taken."})


def email_taken() -> ApiError:
    return ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.", {"email": "An account with this email already exists."})


# ============================================================
# RESPONSE BUILDING
# ============================================================

def _error_response(status_code: int, code: str, message: str, fields: Optional[dict] = None) -> JSONResponse:
    detail = {"code": code, "message": message}
    if fields:
        detail["fields"] = fields
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


_FRIENDLY_TYPE_MESSAGES = {
    "missing": "This field is required.",
    "string_type": "Must be text.",
    "json_invalid": "The request body is not valid JSON.",
    "model_attributes_type": "The request body must be a JSON object.",
    "dict_type": "The request body must be a JSON object.",
}


def _validation_fields(exc: RequestValidationError) -> dict:
    """Turn pydantic errors into { field: friendly message } (first error per field wins)."""
    fields: dict = {}
    for err in exc.errors():
        err_type = err.get("type", "")
        loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        field = "body" if err_type == "json_invalid" or not loc else loc[-1]
        if field in fields:
            continue
        if err_type == "value_error":
            # Our own validators raise ValueError("friendly text"); pydantic prefixes "Value error, "
            message = str(err.get("msg", "")).removeprefix("Value error, ")
        else:
            message = _FRIENDLY_TYPE_MESSAGES.get(err_type, "Invalid value.")
        fields[field] = message
    return fields


# ============================================================
# HANDLER REGISTRATION
# ============================================================

def register_error_handlers(app: FastAPI) -> None:
    """Attach handlers so every error follows the contract format."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Contract: 400 (not FastAPI's default 422). Never echo the submitted values back.
        return _error_response(400, "VALIDATION_ERROR", "Please fix the highlighted fields.", _validation_fields(exc))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log type + path only: request bodies may contain passwords.
        logger.error(f"Unhandled error on {request.method} {request.url.path}: {type(exc).__name__}")
        return _error_response(500, "INTERNAL_ERROR", "Something went wrong. Please try again.")
