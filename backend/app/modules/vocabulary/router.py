from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import UowDep
from backend.app.core.security import owner
from backend.app.modules.vocabulary.schemas import SaveExpression, VocabularyResponse
from backend.app.modules.vocabulary.service import VocabularyService

router = APIRouter(tags=["vocabulary"], dependencies=[Depends(owner)])


@router.get("/vocabulary", operation_id="listVocabulary", response_model=list[VocabularyResponse])
def list_vocabulary(uow: UowDep, due: bool = False) -> list[VocabularyResponse]:
    return VocabularyService(uow).list(due=due)


@router.post("/vocabulary", operation_id="saveExpression", response_model=VocabularyResponse, status_code=201)
def save_expression(body: SaveExpression, uow: UowDep) -> VocabularyResponse:
    return VocabularyService(uow).save(body)
