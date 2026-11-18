from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import UowDep
from backend.app.core.security import owner
from backend.app.modules.practice.schemas import ReviewInput
from backend.app.modules.practice.service import PracticeService
from backend.app.modules.vocabulary.schemas import VocabularyResponse

router = APIRouter(tags=["practice"], dependencies=[Depends(owner)])


@router.post(
    "/vocabulary/{item_id}/reviews", operation_id="reviewExpression", response_model=VocabularyResponse
)
def review(item_id: str, body: ReviewInput, uow: UowDep) -> VocabularyResponse:
    return PracticeService(uow).review(item_id, body)
