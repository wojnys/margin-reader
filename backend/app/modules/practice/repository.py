from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.modules.practice.models import Review


class PracticeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, review_id: str) -> Review | None:
        return self.db.get(Review, review_id)

    def add(self, review: Review) -> None:
        self.db.add(review)
        self.db.flush()
