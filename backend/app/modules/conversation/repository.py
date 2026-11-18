from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.modules.conversation.models import ConversationExpression, ConversationSet


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, session_id: str, revision: int) -> ConversationSet | None:
        return self.db.scalar(
            select(ConversationSet).where(
                ConversationSet.session_id == session_id, ConversationSet.revision == revision
            )
        )

    def add(self, item: ConversationSet) -> ConversationSet:
        self.db.add(item)
        self.db.flush()
        return item

    def cards(self, set_id: str) -> list[ConversationExpression]:
        return list(
            self.db.scalars(
                select(ConversationExpression)
                .where(ConversationExpression.set_id == set_id)
                .order_by(ConversationExpression.source_index)
            )
        )

    def add_card(self, card: ConversationExpression) -> None:
        self.db.add(card)

    def pending(self) -> list[ConversationSet]:
        return list(
            self.db.scalars(select(ConversationSet).where(ConversationSet.status == "pending").limit(10))
        )

    def mark_queued(self, session_id: str, revision: int, attempt: int) -> None:
        self.db.execute(
            update(ConversationSet)
            .where(
                ConversationSet.session_id == session_id,
                ConversationSet.revision == revision,
                ConversationSet.attempt == attempt,
                ConversationSet.status == "pending",
            )
            .values(status="queued")
        )
