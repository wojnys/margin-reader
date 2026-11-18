from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.core.exceptions import DomainError
from backend.app.db.session import UnitOfWork
from backend.app.modules.books.repository import BookRepository
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.knowledge.schemas import (
    BookKnowledge,
    EntityResponse,
    IndexRequested,
    IndexStatus,
    MentionResponse,
    ReviewMention,
)
from backend.app.modules.readings.repository import ReadingRepository


class KnowledgeService:
    def __init__(self, uow: UnitOfWork, config: Settings) -> None:
        self.uow, self.config = uow, config
        self.repo = KnowledgeRepository(uow.session)

    def require(self, book_id: str) -> None:
        if BookRepository(self.uow.session).get(book_id) is None:
            raise DomainError(404, "Book not found")

    def status(self, book_id: str) -> BookKnowledge:
        self.require(book_id)
        jobs = self.repo.jobs(book_id)
        return BookKnowledge(
            jobs=[
                IndexStatus(
                    id=j.id,
                    session_id=j.session_id,
                    revision=j.revision,
                    status=j.status,
                    error=j.error,
                    input_tokens=j.input_tokens,
                    output_tokens=j.output_tokens,
                    estimated_cost=j.estimated_cost,
                    warning=str(j.stages.get("summary_warning"))
                    if isinstance(j.stages.get("summary_warning"), str)
                    else None,
                )
                for j in jobs
            ],
            passages=len(self.repo.sources(book_id)),
            entities=len({m.entity_id for m in self.repo.mentions(book_id) if m.entity_id}),
            unresolved_mentions=sum(m.entity_id is None for m in self.repo.mentions(book_id)),
        )

    def index(self, book_id: str) -> IndexRequested:
        self.require(book_id)
        scheduled = 0
        for reading in ReadingRepository(self.uow.session).list(book_id):
            job = self.repo.enqueue(reading, self.config.embedding_model)
            if job is not None and job.status in {"pending", "failed"}:
                job.status, job.error, job.attempt = "pending", None, job.attempt + 1
                scheduled += 1
        self.uow.commit()
        return IndexRequested(scheduled=scheduled)

    def mentions(self, book_id: str) -> list[MentionResponse]:
        self.require(book_id)
        sources = {p.id: self.repo.source(p, page, job) for p, page, job in self.repo.sources(book_id)}
        return [
            MentionResponse(
                id=m.id,
                surface=m.surface,
                description=m.description,
                kind=m.kind,
                passage_id=m.passage_id,
                resolution=m.resolution,
                entity_id=m.entity_id,
                source=sources.get(m.passage_id),
            )
            for m in self.repo.mentions(book_id)
            if m.resolution != "explicit"
        ]

    def entities(self, book_id: str) -> list[EntityResponse]:
        self.require(book_id)
        active = {m.entity_id for m in self.repo.mentions(book_id) if m.entity_id}
        return [
            EntityResponse(id=e.id, name=e.name, kind=e.kind)
            for e in self.repo.entities(book_id)
            if e.id in active
        ]

    def review(self, book_id: str, mention_id: str, body: ReviewMention) -> MentionResponse:
        self.require(book_id)
        self.repo.lock_book(book_id)
        mentions = {m.id: m for m in self.repo.mentions(book_id)}
        mention = mentions.get(mention_id)
        if mention is None:
            raise DomainError(404, "Mention not found")
        entities = {e.id: e for e in self.repo.entities(book_id)}
        active_entities = {m.entity_id for m in mentions.values() if m.entity_id}
        if body.entity_id and (
            body.entity_id not in active_entities or entities[body.entity_id].kind != mention.kind
        ):
            raise DomainError(422, "Select an entity of the same kind from this book")
        support = (
            next((m for m in mentions.values() if m.entity_id == body.entity_id and m.id != mention.id), None)
            if body.entity_id
            else None
        )
        mention.entity_id, mention.resolution = body.entity_id, "reviewed"
        mention.evidence = [
            value
            for value in dict.fromkeys(
                str(item)
                for item in [
                    mention.passage_id,
                    *([support.passage_id, *support.evidence] if support else []),
                ]
            )
        ]
        # Resubmit every affected current projection (no repeated extraction/model call).
        for job in self.repo.jobs(book_id):
            job.status = "pending"
        self.uow.commit()
        return MentionResponse(
            id=mention.id,
            surface=mention.surface,
            description=mention.description,
            kind=mention.kind,
            passage_id=mention.passage_id,
            resolution=mention.resolution,
            entity_id=mention.entity_id,
        )
