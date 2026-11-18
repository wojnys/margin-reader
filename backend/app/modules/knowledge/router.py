from fastapi import APIRouter, Depends

from backend.app.api.dependencies import RuntimeDep, UowDep
from backend.app.core.security import owner
from backend.app.modules.knowledge.schemas import (
    BookKnowledge,
    EntityResponse,
    IndexRequested,
    MentionResponse,
    ReviewMention,
)
from backend.app.modules.knowledge.service import KnowledgeService

router = APIRouter(tags=["knowledge"], dependencies=[Depends(owner)])


@router.get("/books/{book_id}/knowledge", operation_id="getBookKnowledge", response_model=BookKnowledge)
def status(book_id: str, uow: UowDep, runtime: RuntimeDep) -> BookKnowledge:
    return KnowledgeService(uow, runtime.config).status(book_id)


@router.post(
    "/books/{book_id}/knowledge/index",
    operation_id="indexBookKnowledge",
    response_model=IndexRequested,
    status_code=202,
)
def index(book_id: str, uow: UowDep, runtime: RuntimeDep) -> IndexRequested:
    return KnowledgeService(uow, runtime.config).index(book_id)


@router.get(
    "/books/{book_id}/knowledge/mentions",
    operation_id="listKnowledgeMentions",
    response_model=list[MentionResponse],
)
def mentions(book_id: str, uow: UowDep, runtime: RuntimeDep) -> list[MentionResponse]:
    return KnowledgeService(uow, runtime.config).mentions(book_id)


@router.get(
    "/books/{book_id}/knowledge/entities",
    operation_id="listKnowledgeEntities",
    response_model=list[EntityResponse],
)
def entities(book_id: str, uow: UowDep, runtime: RuntimeDep) -> list[EntityResponse]:
    return KnowledgeService(uow, runtime.config).entities(book_id)


@router.patch(
    "/books/{book_id}/knowledge/mentions/{mention_id}",
    operation_id="reviewKnowledgeMention",
    response_model=MentionResponse,
)
def review(
    book_id: str, mention_id: str, body: ReviewMention, uow: UowDep, runtime: RuntimeDep
) -> MentionResponse:
    return KnowledgeService(uow, runtime.config).review(book_id, mention_id, body)
