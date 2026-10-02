"""Application factory and lifecycle (background jobs, shared services)."""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app import __version__
from app.api.router import api_router
from app.auth.dependencies import CSRF_HEADER
from app.auth.rate_limit import RateLimiter
from app.config import Settings, get_settings
from app.database.session import Database
from app.logging_config import configure_logging
from app.services.alerts.engine import AlertEngine
from app.services.alerts.notifier import CompositeNotifier, LogNotifier, WebSocketNotifier
from app.services.heartbeat import check_heartbeats
from app.services.ingestion import IngestionPipeline
from app.services.retention import run_retention
from app.websocket.hub import Hub

log = logging.getLogger("app")
MAX_BODY_BYTES = 4 * 1024 * 1024


async def _periodic(name: str, interval: float, job: Callable[[], Awaitable[object]]) -> None:
    """Run ``job`` forever; a failure (e.g. database down) is logged, not fatal."""
    while True:
        try:
            await job()
        except Exception:
            log.exception("job.failed", extra={"job": name})
        await asyncio.sleep(interval)


def _start_background_jobs(app: FastAPI) -> list[asyncio.Task[None]]:
    state = app.state
    settings: Settings = state.settings

    async def heartbeat() -> None:
        async with state.db.sessionmaker() as db:
            await check_heartbeats(db, settings, state.alert_engine, state.hub, datetime.now(UTC))

    async def retention() -> None:
        async with state.db.sessionmaker() as db:
            await run_retention(db, settings, datetime.now(UTC))

    return [
        asyncio.create_task(
            _periodic("heartbeat", settings.heartbeat_check_interval_seconds, heartbeat)
        ),
        asyncio.create_task(
            _periodic("retention", settings.retention_job_interval_seconds, retention)
        ),
    ]


def create_app(settings: Settings | None = None, *, background_jobs: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hub = Hub()
        engine = AlertEngine(CompositeNotifier(LogNotifier(), WebSocketNotifier(hub)))
        app.state.settings = settings
        app.state.db = Database(settings)
        app.state.hub = hub
        app.state.alert_engine = engine
        app.state.pipeline = IngestionPipeline(settings, hub, engine)
        app.state.ingest_limiter = RateLimiter(settings.ingest_rate_per_minute, 60)
        app.state.login_limiter = RateLimiter(settings.login_rate_per_minute, 60)
        app.state.started_at = time.monotonic()
        tasks = _start_background_jobs(app) if background_jobs else []
        log.info("app.started", extra={"version": __version__, "env": settings.environment})
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await app.state.db.dispose()
        log.info("app.stopped")

    app = FastAPI(
        title="InfraWatch API",
        version=__version__,
        description="Personal infrastructure monitoring: agent ingestion, history, alerting.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", CSRF_HEADER],
        )
    _install_middleware(app)
    app.include_router(api_router)
    return app


def _install_middleware(app: FastAPI) -> None:
    request_log = logging.getLogger("http")

    @app.middleware("http")
    async def guard_and_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path != "/api/v1/system/health":
            request_log.info(
                "http.request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        return response

    # Only connectivity failures map to 503; constraint violations etc. are bugs
    # and must surface as 500s rather than be retried forever by agents.
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(ConnectionError)
    async def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
        # Agents treat 503 as retryable and keep the samples in their buffer.
        log.error("database.unavailable", extra={"path": request.url.path, "error": str(exc)})
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)
