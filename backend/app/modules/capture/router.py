from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from backend.app.api.dependencies import RuntimeDep, UowDep
from backend.app.core.schemas import OkResponse
from backend.app.core.security import owner
from backend.app.modules.capture.schemas import BatchCaptureResponse, CaptureResponse, PairingResponse
from backend.app.modules.capture.service import CaptureService

router = APIRouter(tags=["capture"])


@router.post(
    "/books/{book_id}/pair",
    operation_id="pairPhone",
    response_model=PairingResponse,
    dependencies=[Depends(owner)],
)
def pair(book_id: str, request: Request, uow: UowDep, runtime: RuntimeDep) -> PairingResponse:
    return CaptureService(uow, runtime.config).pair(book_id, request.url.port or 80)


@router.get("/capture/{token}", operation_id="getCapture", response_model=CaptureResponse)
def info(token: str, uow: UowDep, runtime: RuntimeDep) -> CaptureResponse:
    return CaptureService(uow, runtime.config).info(token)


@router.post("/capture/{token}", operation_id="uploadCapture", response_model=OkResponse, status_code=201)
async def upload(
    token: str,
    uow: UowDep,
    runtime: RuntimeDep,
    image: Annotated[UploadFile, File()],
    page_label: Annotated[str, Form()] = "",
) -> OkResponse:
    await CaptureService(uow, runtime.config).upload(
        token, await image.read(20 * 1024 * 1024 + 1), page_label
    )
    return OkResponse()


@router.post(
    "/capture/{token}/batch",
    operation_id="uploadCaptureBatch",
    response_model=BatchCaptureResponse,
    status_code=201,
)
async def upload_batch(
    token: str,
    uow: UowDep,
    runtime: RuntimeDep,
    images: Annotated[list[UploadFile], File()],
    page_labels: Annotated[list[str], Form()],
) -> BatchCaptureResponse:
    try:
        return await CaptureService(uow, runtime.config).upload_batch(token, images, page_labels)
    finally:
        for image in images:
            await image.close()
