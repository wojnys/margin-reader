from __future__ import annotations

from backend.app.core.exceptions import DomainError
from backend.app.db.session import UnitOfWork
from backend.app.modules.conversation.models import ConversationSet
from backend.app.modules.conversation.repository import ConversationRepository
from backend.app.modules.conversation.schemas import ConversationCard, ConversationResponse
from backend.app.modules.readings.repository import ReadingRepository


class ConversationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repository = ConversationRepository(uow.session)

    def response(self, session_id: str, revision: int) -> ConversationResponse | None:
        item = self.repository.get(session_id, revision)
        if item is None:
            return None
        return ConversationResponse.model_validate(
            {
                "status": item.status,
                "error": item.error,
                "cards": [
                    ConversationCard.model_validate(card.payload) for card in self.repository.cards(item.id)
                ],
            }
        )

    def request(self, session_id: str, revision: int) -> ConversationResponse:
        reading = ReadingRepository(self.uow.session).get(session_id)
        if reading is None:
            raise DomainError(404, "Reading not found")
        if reading.revision != revision or reading.status != "complete" or not reading.learning:
            raise DomainError(
                409, "Wait for this reading to finish and refresh before generating conversation examples"
            )
        if reading.image_path == "sample":
            raise DomainError(409, "Upload your own pages to generate conversation examples")
        item = self.repository.get(session_id, revision)
        if item is None:
            item = self.repository.add(ConversationSet(session_id=session_id, revision=revision))
        elif item.status == "failed":
            item.status, item.error = "pending", None
            item.attempt += 1
        self.uow.commit()
        result = self.response(session_id, revision)
        assert result is not None
        return result
