"""Import-safe app factory. Resources are opened only by the runtime lifespan."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import router
from backend.app.core.body_limits import BatchBodyLimitMiddleware
from backend.app.core.config import settings
from backend.app.core.exceptions import DomainError
from backend.app.core.runtime import Runtime, RuntimeApp
from backend.app.db.session import create_database
from backend.app.temporal.dispatcher import dispatch_pending


def load_runtime() -> Runtime:
    config = settings()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "uploads").mkdir(exist_ok=True)
    secret_file = config.data_dir / "owner.secret"
    if not secret_file.exists():
        try:
            with secret_file.open("x") as file:
                file.write(secrets.token_urlsafe(48))
            secret_file.chmod(0o600)
        except FileExistsError:
            pass
    return Runtime(config, create_database(config.database_url), secret_file.read_text().strip())


def create_app(
    runtime: Runtime | None = None, *, background_jobs: bool = True, serve_frontend: bool = True
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: RuntimeApp) -> AsyncGenerator[None]:
        resolved = runtime or load_runtime()
        app.runtime = resolved
        dispatcher = asyncio.create_task(dispatch_pending(resolved)) if background_jobs else None
        try:
            yield
        finally:
            if dispatcher:
                dispatcher.cancel()
                try:
                    await dispatcher
                except asyncio.CancelledError:
                    pass

    app = RuntimeApp(title="Margin Reader", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BatchBodyLimitMiddleware)
    if runtime is not None:
        app.runtime = runtime
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if serve_frontend and (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(dist / "index.html")

    return app
