from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500

    def __init__(self, message: str, *, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ConnectionTestError(AppError):
    """Raised when a connector fails to connect or authenticate."""
    status_code = 502


class NotFoundError(AppError):
    status_code = 404


class ScanError(AppError):
    status_code = 500


class ParsingError(AppError):
    status_code = 422


class ValidationFailedError(AppError):
    status_code = 400


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
        )
