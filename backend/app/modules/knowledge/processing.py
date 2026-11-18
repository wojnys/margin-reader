from __future__ import annotations

import asyncio
import json
from typing import cast

from pydantic import JsonValue
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from backend.app.ai.client import ConfigurationError, Metrics, OutputValidationError
from backend.app.core.config import Settings
from backend.app.db.base import uid
from backend.app.db.session import SessionFactory
from backend.app.knowledge import extraction
from backend.app.knowledge.chunking import tokens
from backend.app.knowledge.embeddings import Embedder, embedder
from backend.app.knowledge.graph import GraphStore, Neo4jStore
from backend.app.modules.knowledge.models import (
    IndexJob,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeSummary,
    Mention,
)
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.knowledge.schemas import ExtractedKnowledge, Resolutions
from backend.app.modules.readings.models import ReadingSession
from backend.app.temporal.activities import with_heartbeats


class KnowledgeProcessor:
    def __init__(
        self,
        sessions: SessionFactory,
        config: Settings,
        encoder: Embedder | None = None,
        graph: GraphStore | None = None,
    ) -> None:
        self.sessions, self.config, self.encoder, self.graph = sessions, config, encoder, graph

    def current(self, repo: KnowledgeRepository, job_id: str) -> IndexJob:
        job = repo.job(job_id)
        reading = repo.db.get(ReadingSession, job.session_id) if job else None
        if job is None or reading is None or reading.knowledge_job_id != job.id:
            raise ApplicationError("Source text was replaced or removed", non_retryable=True)
        return job

    @staticmethod
    def usage(job: IndexJob, metrics: Metrics) -> None:
        job.input_tokens += metrics["input_tokens"]
        job.output_tokens += metrics["output_tokens"]
        job.estimated_cost += metrics["estimated_cost"]

    async def run(self, job_id: str) -> None:
        with self.sessions() as db:
            repo = KnowledgeRepository(db)
            job = self.current(repo, job_id)
            if job.status == "ready":
                return
            repo.prepare(job)
            job.status, job.error = "embedding", None
            db.commit()
            rows = repo.passages(job.id)
            missing = [(p.id, p.text) for p in rows if p.embedding is None]
            model = job.embedding_model
        if missing:
            encoder = self.encoder or await asyncio.to_thread(embedder, model)
            vectors = await asyncio.to_thread(encoder.encode, [p[1] for p in missing])
            if len(vectors) != len(missing) or any(len(v) != 1024 for v in vectors):
                raise ApplicationError("Embedding output has an invalid shape", non_retryable=True)
            with self.sessions() as db:
                repo = KnowledgeRepository(db)
                job = self.current(repo, job_id)
                by_id = {p.id: p for p in repo.passages(job_id)}
                for (pid, _), vector in zip(missing, vectors, strict=True):
                    by_id[pid].embedding = vector
                    repo.fill_keywords(by_id[pid])
                db.commit()
        with self.sessions() as db:
            repo = KnowledgeRepository(db)
            job = self.current(repo, job_id)
            sources = [repo.source(p, page, j) for p, page, j in repo.sources(job.book_id) if j.id == job_id]
            cached = job.stages.get("extraction")
            job.status = "extracting"
            db.commit()
        if cached is None:
            if self.graph is None:
                store = Neo4jStore(self.config)
                try:
                    await asyncio.to_thread(store.verify)
                finally:
                    store.driver.close()
            result, metrics = await extraction.extract(sources, self.config)
            with self.sessions() as db:
                job = self.current(KnowledgeRepository(db), job_id)
                job.stages = {
                    **job.stages,
                    "extraction": cast(dict[str, JsonValue], result.model_dump(mode="json")),
                }
                self.usage(job, metrics)
                db.commit()
        else:
            result = ExtractedKnowledge.model_validate(cached)
        with self.sessions() as db:
            for side, value in (("left", result.left_summary), ("right", result.right_summary)):
                if (
                    value
                    and db.scalar(
                        select(KnowledgeSummary.id).where(
                            KnowledgeSummary.job_id == job_id, KnowledgeSummary.side == side
                        )
                    )
                    is None
                ):
                    db.add(KnowledgeSummary(job_id=job_id, side=side, text=value))
            db.commit()
        await self.reconcile(job_id, result)
        from backend.app.knowledge.summaries import build

        with self.sessions() as db:
            job = self.current(KnowledgeRepository(db), job_id)
            book_id = job.book_id
            summary_failed = bool(job.stages.get("summary_warning"))
            job.status = "summarizing"
            db.commit()
        if not summary_failed:
            try:
                await build(self.sessions, self.config, book_id, job_id)
            except (UnexpectedModelBehavior, ModelAPIError, ConfigurationError) as exc:
                # Derived recaps are optional. A provider failure here must not
                # discard already grounded entities or prevent graph publication.
                with self.sessions() as db:
                    job = self.current(KnowledgeRepository(db), job_id)
                    if isinstance(exc, OutputValidationError):
                        self.usage(job, exc.metrics)
                        reason = str(exc)[:350]
                    else:
                        reason = type(exc).__name__
                    job.stages = {
                        **job.stages,
                        "summary_warning": "Graph ready; a generated section recap is unavailable. " + reason,
                    }
                    db.commit()
        await self.synchronize(job_id)

    async def reconcile(self, job_id: str, result: ExtractedKnowledge) -> None:
        with self.sessions() as db:
            repo = KnowledgeRepository(db)
            job = self.current(repo, job_id)
            if job.stages.get("resolved"):
                return
            repo.lock_book(job.book_id)
            existing = list(db.scalars(select(Mention).where(Mention.job_id == job_id)))
            if not existing:
                for item in result.mentions:
                    entity_id = None
                    # A topic/event occurrence can stand on its own without a proper
                    # name. A generic person/role still needs identity evidence.
                    anchored = item.named or item.kind in {"topic", "event"}
                    if anchored:
                        entity_id = uid()
                        db.add(
                            KnowledgeEntity(
                                id=entity_id, book_id=job.book_id, name=item.surface[:200], kind=item.kind
                            )
                        )
                        db.flush()
                    db.add(
                        Mention(
                            job_id=job_id,
                            local_id=item.local_id,
                            passage_id=item.passage_id,
                            surface=item.surface,
                            kind=item.kind,
                            description=item.description,
                            named=item.named,
                            entity_id=entity_id,
                            resolution="explicit" if anchored else "unresolved",
                            evidence=[item.passage_id] if anchored else [],
                        )
                    )
                db.flush()
                mapping = {
                    m.local_id: m.id for m in db.scalars(select(Mention).where(Mention.job_id == job_id))
                }
                for claim in result.claims:
                    db.add(
                        KnowledgeClaim(
                            job_id=job_id,
                            subject_id=mapping[claim.subject],
                            object_id=mapping[claim.object],
                            relation=claim.relation,
                            description=claim.description,
                            evidence=list(claim.passage_ids),
                        )
                    )
            job.status = "resolving"
            db.commit()
            # Candidate registry is book-scoped. Prioritize original passages by semantic
            # similarity and lexical overlap; never send the whole book/entity registry.
            all_mentions = repo.mentions(job.book_id)
            entities = {e.id: e for e in repo.entities(job.book_id)}
            source_rows = repo.sources(job.book_id)
            source_map = {p.id: repo.source(p, page, j) for p, page, j in source_rows}
            for mention in all_mentions:
                if (
                    mention.resolution == "inferred"
                    and not set(str(v) for v in mention.evidence) <= source_map.keys()
                ):
                    mention.entity_id, mention.resolution, mention.evidence = None, "unresolved", []
                    affected = repo.job(mention.job_id)
                    if affected is not None and affected.id != job_id:
                        affected.status = "pending"
            new = [m for m in all_mentions if m.job_id == job_id and m.resolution != "reviewed"]
            kinds = {m.kind for m in new}
            new.extend(
                [
                    m
                    for m in all_mentions
                    if m.job_id != job_id
                    and m.entity_id is None
                    and m.kind in kinds
                    and m.resolution != "reviewed"
                ][:20]
            )
            db.commit()
            vectors = {p.id: list(p.embedding) for p, _, _ in source_rows if p.embedding is not None}
            evidence_ids = {m.passage_id for m in new}
            candidate_ids: set[str] = set()
            for mention in new:
                words = set((mention.surface + " " + mention.description).lower().split())
                vector = vectors.get(mention.passage_id, [])

                def score(other: Mention) -> float:
                    lexical = len(words & set((other.surface + " " + other.description).lower().split()))
                    semantic = sum(a * b for a, b in zip(vector, vectors.get(other.passage_id, [])))
                    return lexical + semantic

                candidates = [
                    m
                    for m in all_mentions
                    if m.entity_id
                    and (m.named or m.kind in {"topic", "event"})
                    and m.kind == mention.kind
                    and m.id != mention.id
                ]
                for candidate in sorted(candidates, key=score, reverse=True)[:5]:
                    if candidate.entity_id:
                        candidate_ids.add(candidate.entity_id)
                        evidence_ids.add(candidate.passage_id)
            payload: dict[str, JsonValue] = {
                "mentions": [
                    {"id": m.id, "text": m.surface, "description": m.description, "passage_id": m.passage_id}
                    for m in new
                ],
                "candidates": [
                    {"id": e.id, "name": e.name, "kind": e.kind}
                    for e in entities.values()
                    if e.id in candidate_ids
                ],
                "passages": [
                    s.model_dump(mode="json") for pid, s in source_map.items() if pid in evidence_ids
                ],
            }
            allowed_mentions = {m.id: m for m in new}
            candidate_support = {
                eid: {m.passage_id for m in all_mentions if m.entity_id == eid} for eid in candidate_ids
            }
        # Expansion is bounded. Oversized/ambiguous cases keep their explicit/unresolved state.
        metrics: Metrics
        if candidate_ids and tokens(json.dumps(payload)) <= 9000:
            decisions, metrics = await extraction.resolve(json.dumps(payload), self.config)
        else:
            decisions = Resolutions(decisions=[])
            metrics = Metrics(input_tokens=0, output_tokens=0, estimated_cost=0.0)
        with self.sessions() as db:
            repo = KnowledgeRepository(db)
            job = self.current(repo, job_id)
            repo.lock_book(job.book_id)
            for decision in decisions.decisions:
                mention = allowed_mentions.get(decision.mention_id)
                evidence = set(decision.evidence_ids)
                if mention is None or decision.entity_id is None:
                    continue
                if (
                    decision.entity_id not in candidate_ids
                    or not evidence <= evidence_ids
                    or mention.passage_id not in evidence
                    or not evidence & candidate_support[decision.entity_id]
                ):
                    continue
                target = db.get(KnowledgeEntity, decision.entity_id)
                current = db.get(Mention, decision.mention_id)
                if (
                    current is not None
                    and current.resolution != "reviewed"
                    and target is not None
                    and target.book_id == job.book_id
                    and target.kind == current.kind
                ):
                    current.entity_id, current.resolution = target.id, "inferred"
                    current.evidence = list(decision.evidence_ids)
                    affected = repo.job(current.job_id)
                    if affected is not None and affected.id != job_id:
                        affected.status = "pending"
            self.usage(job, metrics)
            job.stages = {**job.stages, "resolved": True}
            db.commit()

    async def synchronize(self, job_id: str) -> None:
        with self.sessions() as db:
            repo = KnowledgeRepository(db)
            job = self.current(repo, job_id)
            job.status = "syncing"
            db.commit()
            mentions = {m.id: m for m in repo.mentions(job.book_id)}
            relevant_entities = {m.entity_id for m in mentions.values() if m.job_id == job_id}
            claims: list[dict[str, JsonValue]] = []
            for c in repo.claims(job.book_id):
                s, o = mentions.get(c.subject_id), mentions.get(c.object_id)
                if c.job_id == job_id and s and o and s.entity_id and o.entity_id:
                    # Include resolution evidence too; later answers must be able to verify identity.
                    evidence = list(dict.fromkeys(str(v) for v in [*c.evidence, *s.evidence, *o.evidence]))
                    relevant_entities.update([s.entity_id, o.entity_id])
                    claims.append(
                        {
                            "id": c.id,
                            "subject": s.entity_id,
                            "object": o.entity_id,
                            "relation": c.relation,
                            "description": c.description,
                            "evidence": cast(list[JsonValue], evidence),
                        }
                    )
            entities = [
                {"id": e.id, "name": e.name, "kind": e.kind}
                for e in repo.entities(job.book_id)
                if e.id in relevant_entities
            ]
            book_id = job.book_id
        store = self.graph or Neo4jStore(self.config)
        await asyncio.to_thread(
            store.sync, book_id, job_id, cast(list[dict[str, JsonValue]], entities), claims
        )
        with self.sessions() as db:
            job = self.current(KnowledgeRepository(db), job_id)
            job.status, job.error = "ready", None
            db.commit()

    @activity.defn(name="index_reading")
    async def index_activity(self, job_id: str) -> None:
        try:
            await with_heartbeats(self.run(job_id))
        except ApplicationError:
            raise
        except OutputValidationError as exc:
            # The model already had a bounded correction attempt. Replaying the
            # same rejected output three more times wastes paid API requests.
            with self.sessions() as db:
                job = KnowledgeRepository(db).job(job_id)
                if job is not None:
                    self.usage(job, exc.metrics)
                    db.commit()
            raise ApplicationError(
                f"Knowledge indexing could not validate the AI response. {str(exc)[:1000]}",
                type="KnowledgeOutputValidationError",
                non_retryable=True,
            ) from None
        except Exception as exc:
            from pydantic_ai.exceptions import ModelHTTPError

            from backend.app.ai.client import ConfigurationError

            status = exc.status_code if isinstance(exc, ModelHTTPError) else None
            terminal = isinstance(exc, (ConfigurationError, ValueError)) or status in {
                400,
                401,
                402,
                403,
                404,
                413,
                422,
            }
            reason = f"Provider HTTP {status}" if status else type(exc).__name__
            raise ApplicationError(
                f"Knowledge indexing failed ({reason}). Check model, embedding and Neo4j settings.",
                non_retryable=terminal,
            ) from None

    @activity.defn(name="fail_indexing")
    async def fail_activity(self, payload: dict[str, str]) -> None:
        with self.sessions() as db:
            job = KnowledgeRepository(db).job(payload["id"])
            if job is not None:
                job.status, job.error = (
                    "failed",
                    payload.get(
                        "message", "Indexing stopped. Check worker/model/graph configuration and retry."
                    )[:500],
                )
                db.commit()
