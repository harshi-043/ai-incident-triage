"""
One error format for the whole API:

    {"error": {"code": "source_not_found", "message": "...", "details": null}}

Handlers never put internal details (stack traces, file paths, SQL) in a response.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("triage")

# Every public id looks like "src_1a2b3c4d5e6f7a8b" (a short prefix, then 16 hex characters).
ID_PATTERN = re.compile(r"^[a-z]{2,4}_[0-9a-f]{16}$")


class AppError(Exception):
    """An error with an HTTP status, a stable machine-readable code and a safe message."""

    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def not_found(what: str, identifier: str | int) -> AppError:
    return AppError(404, f"{what}_not_found", f"No {what.replace('_', ' ')} with id '{identifier}' was found.")


def bad_id(what: str, identifier: str) -> AppError:
    """Malformed ids are rejected before the database is touched."""
    return AppError(422, "invalid_id", f"'{identifier[:40]}' is not a valid {what.replace('_', ' ')} id.")


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _simplify_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only where the problem is and what it is (no echo of the submitted values)."""
    return [
        {"field": ".".join(str(part) for part in e.get("loc", []) if part != "body"), "problem": str(e.get("msg", ""))}
        for e in errors
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            "validation_error",
            "The request is not valid. Check the listed fields.",
            _simplify_validation_errors(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}
        return error_response(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return error_response(500, "database_error", "A database error occurred. Please try again.")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The full traceback goes to the server log only, never to the response.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "An unexpected error occurred.")
