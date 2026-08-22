from contextlib import asynccontextmanager
import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import get_settings
from .db import init_db
from .security import redact_sensitive_data, safe_error_payload
from . import models  # noqa: F401


logger = logging.getLogger("recoveriq.api")


def _setup_logging(level: str, *, log_sql_queries: bool) -> None:
    normalized = level.upper()
    resolved_level = getattr(logging, normalized, logging.DEBUG)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("uvicorn").setLevel(resolved_level)
    if log_sql_queries:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if resolved_level <= logging.DEBUG else logging.WARNING)
    else:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    _setup_logging(settings.log_level, log_sql_queries=settings.log_sql_queries)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def trace_http_requests(request: Request, call_next):
        started = perf_counter()
        request_meta = redact_sensitive_data(
            {
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
            }
        )
        logger.debug("HTTP request started: %s", request_meta)

        response = await call_next(request)

        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        logger.debug(
            "HTTP request completed: %s",
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        fields = [".".join([str(item) for item in err.get("loc", []) if item != "body"]) for err in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "fields": [field for field in fields if field],
                },
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        code = "HTTP_ERROR"
        if exc.status_code == 401:
            code = "UNAUTHORIZED"
        elif exc.status_code == 403:
            code = "FORBIDDEN"
        elif exc.status_code == 404:
            code = "NOT_FOUND"
        elif exc.status_code == 422:
            code = "VALIDATION_ERROR"
        elif exc.status_code >= 500:
            code = "SERVER_ERROR"

        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(status_code=exc.status_code, content=safe_error_payload(code=code, message=detail))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled server error",
            extra={
                "request": redact_sensitive_data(
                    {
                        "path": str(request.url.path),
                        "method": request.method,
                        "query": dict(request.query_params),
                        "error_type": type(exc).__name__,
                    }
                )
            },
        )
        return JSONResponse(
            status_code=500,
            content=safe_error_payload(code="INTERNAL_SERVER_ERROR", message="An unexpected server error occurred."),
        )

    app.include_router(router)
    app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
