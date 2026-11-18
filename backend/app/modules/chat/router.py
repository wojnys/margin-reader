from fastapi import APIRouter, Depends

from backend.app.api.dependencies import UowDep
from backend.app.core.security import owner
from backend.app.modules.chat.schemas import (
    CreateThread,
    SendMessage,
    ThreadDetail,
    ThreadResponse,
    TurnResponse,
)
from backend.app.modules.chat.service import ChatService

router = APIRouter(tags=["chat"], dependencies=[Depends(owner)])


@router.get("/books/{book_id}/chats", operation_id="listBookChats", response_model=list[ThreadResponse])
def list_chats(book_id: str, uow: UowDep) -> list[ThreadResponse]:
    return ChatService(uow).list(book_id)


@router.post(
    "/books/{book_id}/chats", operation_id="createBookChat", response_model=ThreadResponse, status_code=201
)
def create_chat(book_id: str, body: CreateThread, uow: UowDep) -> ThreadResponse:
    return ChatService(uow).create(book_id, body)


@router.get("/chats/{thread_id}", operation_id="getBookChat", response_model=ThreadDetail)
def get_chat(thread_id: str, uow: UowDep) -> ThreadDetail:
    return ChatService(uow).detail(thread_id)


@router.post(
    "/chats/{thread_id}/messages",
    operation_id="sendBookChatMessage",
    response_model=TurnResponse,
    status_code=202,
)
def send_message(thread_id: str, body: SendMessage, uow: UowDep) -> TurnResponse:
    return ChatService(uow).send(thread_id, body)


@router.post(
    "/chats/{thread_id}/messages/{turn_id}/retry",
    operation_id="retryBookChatMessage",
    response_model=TurnResponse,
    status_code=202,
)
def retry_message(thread_id: str, turn_id: str, uow: UowDep) -> TurnResponse:
    return ChatService(uow).retry(thread_id, turn_id)
