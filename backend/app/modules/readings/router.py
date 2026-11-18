from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from backend.app.api.dependencies import RuntimeDep, UowDep
from backend.app.core.security import owner
from backend.app.modules.conversation.schemas import ConversationResponse, GenerateConversation
from backend.app.modules.conversation.service import ConversationService
from backend.app.modules.readings.schemas import CorrectText, ReadingResponse, RefreshLearning, SampleResponse
from backend.app.modules.readings.service import ReadingService

router = APIRouter(tags=["readings"], dependencies=[Depends(owner)])


@router.post("/sample", operation_id="createSample", response_model=SampleResponse)
def sample(uow: UowDep, runtime: RuntimeDep) -> SampleResponse:
    return ReadingService(uow, runtime.config).sample()


@router.get("/books/{book_id}/sessions", operation_id="listReadings", response_model=list[ReadingResponse])
def list_readings(book_id: str, uow: UowDep, runtime: RuntimeDep) -> list[ReadingResponse]:
    return ReadingService(uow, runtime.config).list(book_id)


@router.post(
    "/books/{book_id}/sessions", operation_id="uploadReading", response_model=ReadingResponse, status_code=201
)
async def upload_reading(
    book_id: str,
    uow: UowDep,
    runtime: RuntimeDep,
    image: Annotated[UploadFile, File()],
    page_label: Annotated[str, Form()] = "",
) -> ReadingResponse:
    return await ReadingService(uow, runtime.config).upload(
        book_id, await image.read(20 * 1024 * 1024 + 1), page_label
    )


@router.get(
    "/sessions/{session_id}/image",
    operation_id="getReadingImage",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}},
)
def image(session_id: str, uow: UowDep, runtime: RuntimeDep) -> FileResponse:
    return FileResponse(ReadingService(uow, runtime.config).image(session_id), media_type="image/jpeg")


@router.post("/sessions/{session_id}/retry", operation_id="retryReading", response_model=ReadingResponse)
def retry(session_id: str, uow: UowDep, runtime: RuntimeDep) -> ReadingResponse:
    return ReadingService(uow, runtime.config).retry(session_id)


@router.post(
    "/sessions/{session_id}/learning", operation_id="refreshReadingLearning", response_model=ReadingResponse
)
def refresh_learning(
    session_id: str, body: RefreshLearning, uow: UowDep, runtime: RuntimeDep
) -> ReadingResponse:
    return ReadingService(uow, runtime.config).refresh_learning(session_id, body)


@router.put("/sessions/{session_id}/text", operation_id="correctReadingText", response_model=ReadingResponse)
def correct_text(session_id: str, body: CorrectText, uow: UowDep, runtime: RuntimeDep) -> ReadingResponse:
    return ReadingService(uow, runtime.config).correct_text(session_id, body)


@router.post(
    "/sessions/{session_id}/conversation",
    operation_id="generateReadingConversation",
    response_model=ConversationResponse,
    status_code=202,
)
def generate_conversation(session_id: str, body: GenerateConversation, uow: UowDep) -> ConversationResponse:
    return ConversationService(uow).request(session_id, body.revision)
