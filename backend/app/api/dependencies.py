from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request

from backend.app.core.runtime import Runtime, RuntimeApp
from backend.app.db.session import UnitOfWork


def get_runtime(request: Request) -> Runtime:
    # Starlette's state is an untyped extension point; validate it once here.
    app: object = request.scope["app"]  # pyright: ignore[reportAny] -- ASGI scope is library-typed Any
    value = app.runtime if isinstance(app, RuntimeApp) else None
    if not isinstance(value, Runtime):
        raise RuntimeError("Application lifespan has not initialized runtime dependencies")
    return value


def get_uow(runtime: Annotated[Runtime, Depends(get_runtime)]) -> Generator[UnitOfWork, None, None]:
    with runtime.sessions() as session:
        yield UnitOfWork(session)


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
UowDep = Annotated[UnitOfWork, Depends(get_uow)]
