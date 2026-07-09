"""Stable public error envelope; internal exception details stay server-side."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("aeroroute.errors")
logger.setLevel(logging.ERROR)
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)


class PublicAPIError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PublicAPIError)
    async def public_api_error(
        _: Request, error: PublicAPIError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": error.errors(),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(
        request: Request, error: SQLAlchemyError
    ) -> JSONResponse:
        _log_unhandled(request, error)
        return _database_unavailable_response()

    @app.exception_handler(OSError)
    async def database_os_error(
        request: Request, error: OSError
    ) -> JSONResponse:
        _log_unhandled(request, error)
        return _database_unavailable_response()


def _log_unhandled(request: Request, error: Exception) -> None:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "unhandled_exception request_id=%s method=%s path=%s "
        "exception=%s.%s message=%s",
        request_id,
        request.method,
        request.url.path,
        type(error).__module__,
        type(error).__qualname__,
        str(error),
        exc_info=error,
    )


def _database_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "code": "database_unavailable",
            "message": (
                "The flight-planning database is temporarily unavailable."
            ),
        },
    )
