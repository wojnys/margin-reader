from __future__ import annotations

from datetime import timedelta

from backend.app.core.exceptions import DomainError
from backend.app.db.base import now
from backend.app.db.session import UnitOfWork
from backend.app.modules.practice.models import Review
from backend.app.modules.practice.repository import PracticeRepository
from backend.app.modules.practice.schemas import ReviewInput
from backend.app.modules.vocabulary.schemas import VocabularyResponse
from backend.app.modules.vocabulary.service import VocabularyService


class PracticeService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repository = PracticeRepository(uow.session)
        self.vocabulary = VocabularyService(uow)

    def review(self, item_id: str, body: ReviewInput) -> VocabularyResponse:
        item = self.vocabulary.repository.get(item_id, for_update=True)
        if item is None:
            raise DomainError(404, "Expression not found")
        prior = self.repository.get(body.id)
        if prior:
            if prior.vocabulary_id != item_id or prior.rating != body.rating:
                raise DomainError(409, "Review identifier already used")
            return self.vocabulary.response(item)
        if body.rating == 0:
            item.interval_days, item.repetitions = 0, 0
            item.due_at = now() + timedelta(minutes=10)
        else:
            multiplier = {1: 1.2, 2: 2.2, 3: 3.0}[body.rating]
            initial = {1: 1, 2: 2, 3: 4}[body.rating]
            item.interval_days = min(365, max(initial, round(item.interval_days * multiplier)))
            item.repetitions += 1
            item.due_at = now() + timedelta(days=item.interval_days)
        self.repository.add(Review(id=body.id, vocabulary_id=item_id, rating=body.rating))
        result = self.vocabulary.response(item)
        self.uow.commit()
        return result
