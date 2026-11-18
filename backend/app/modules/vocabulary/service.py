from __future__ import annotations

import hashlib

from backend.app.ai.schemas import Learning
from backend.app.core.exceptions import DomainError
from backend.app.db.session import UnitOfWork
from backend.app.modules.readings.repository import ReadingRepository
from backend.app.modules.vocabulary.models import Vocabulary, VocabularySource
from backend.app.modules.vocabulary.repository import VocabularyRepository
from backend.app.modules.vocabulary.schemas import SaveExpression, VocabularyResponse


class VocabularyService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repository = VocabularyRepository(uow.session)
        self.readings = ReadingRepository(uow.session)

    def response(self, item: Vocabulary) -> VocabularyResponse:
        source_sentence, book_title = self.repository.source_context(item.id)
        return VocabularyResponse(
            id=item.id,
            expression=item.expression,
            meaning_cs=item.meaning_cs,
            explanation_cs=item.explanation_cs,
            example_en=item.example_en,
            example_cs=item.example_cs,
            kind=item.kind,
            level=item.level,
            source_sentence=source_sentence,
            book_title=book_title,
            due_at=item.due_at.isoformat() + "Z",
            repetitions=item.repetitions,
        )

    def list(self, *, due: bool = False) -> list[VocabularyResponse]:
        return [self.response(item) for item in self.repository.list(due=due)]

    def save(self, body: SaveExpression) -> VocabularyResponse:
        reading = self.readings.get(body.session_id)
        if reading is None:
            raise DomainError(404, "Reading not found")
        if reading.revision != body.revision or reading.status != "complete" or not reading.learning:
            raise DomainError(409, "Refresh this reading before saving an expression")
        learning = Learning.model_validate(reading.learning)
        if body.index >= len(learning.expressions):
            raise DomainError(422, "Expression not found")
        expression = learning.expressions[body.index]
        identity = hashlib.sha256(
            (
                expression.expression.strip().casefold() + "\n" + expression.meaning_cs.strip().casefold()
            ).encode()
        ).hexdigest()
        item = self.repository.by_identity(identity)
        if item is None:
            item = self.repository.add(
                Vocabulary(
                    identity=identity,
                    expression=expression.expression,
                    meaning_cs=expression.meaning_cs,
                    explanation_cs=expression.explanation_cs,
                    example_en=expression.example_en,
                    example_cs=expression.example_cs,
                    kind=expression.kind,
                    level=expression.level,
                )
            )
        if not self.repository.has_source(item.id, reading.id, reading.revision):
            self.repository.add_source(
                VocabularySource(
                    vocabulary_id=item.id,
                    session_id=reading.id,
                    revision=reading.revision,
                    source_sentence=expression.source_sentence,
                    page_side=expression.page_side,
                )
            )
        result = self.response(item)
        self.uow.commit()
        return result
