from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, Response

from backend.app.api.dependencies import RuntimeDep
from backend.app.core.schemas import ErrorResponse, OkResponse, SystemResponse, ValidationErrorResponse
from backend.app.core.security import owner, require_localhost
from backend.app.modules.books.router import router as books
from backend.app.modules.capture.router import router as capture
from backend.app.modules.chat.router import router as chat
from backend.app.modules.knowledge.router import router as knowledge
from backend.app.modules.practice.router import router as practice
from backend.app.modules.readings.router import router as readings
from backend.app.modules.vocabulary.router import router as vocabulary
from backend.app.temporal.dispatcher import connect_temporal

router = APIRouter(
    prefix="/api",
    responses={
        **{code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 410, 413)},
        422: {"model": ValidationErrorResponse},
    },
)


@router.get("/health", tags=["system"], operation_id="getHealth", response_model=OkResponse)
def health() -> OkResponse:
    return OkResponse()


@router.post("/bootstrap", tags=["system"], operation_id="bootstrapOwner", response_model=OkResponse)
def bootstrap(request: Request, response: Response, runtime: RuntimeDep) -> OkResponse:
    require_localhost(request)
    response.set_cookie(
        "margin_owner",
        runtime.owner_secret,
        httponly=True,
        samesite="strict",
        path="/api",
        max_age=365 * 86400,
    )
    return OkResponse()


@router.get(
    "/system",
    tags=["system"],
    operation_id="getSystem",
    response_model=SystemResponse,
    dependencies=[Depends(owner)],
)
async def system(runtime: RuntimeDep) -> SystemResponse:
    connected = False
    try:
        client = await connect_temporal(runtime.config)
        await asyncio.wait_for(client.service_client.check_health(), 3)
        connected = True
    except Exception:
        pass
    return SystemResponse(
        api_key_configured=bool(runtime.config.deepinfra_api_key.get_secret_value()),
        model=runtime.config.deepinfra_model,
        temporal_connected=connected,
    )


for feature in (books, readings, vocabulary, practice, capture, chat, knowledge):
    router.include_router(feature)
