"""Knowledge ingestion/retrieval with synthetic text and no paid AI requests."""

import json
import os
from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai import chat
from backend.app.ai.client import Metrics
from backend.app.core.config import Settings
from backend.app.knowledge import extraction, retrieval
from backend.app.knowledge.chunking import chunks, content_hash
from backend.app.knowledge.graph import Neo4jStore
from backend.app.modules.chat.schemas import AnswerCitation, BookAnswer, SourcePassage
from backend.app.modules.knowledge.models import IndexJob, KnowledgeEntity, Mention
from backend.app.modules.knowledge.processing import KnowledgeProcessor
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.knowledge.schemas import (
    ExtractedClaim,
    ExtractedKnowledge,
    ExtractedMention,
    ResolutionDecision,
    Resolutions,
)
from backend.app.modules.readings.models import ReadingSession


class Encoder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0] + [0.0] * 1022
            if any(word in text.lower() for word in ["refus", "declin"])
            else [0.0, 1.0] + [0.0] * 1022
            for text in texts
        ]


class Graph:
    def __init__(self) -> None:
        self.calls = 0
        self.claims = {}
        self.fail = False

    def sync(
        self,
        book_id: str,
        job_id: str,
        entities: list[dict[str, JsonValue]],
        claims: list[dict[str, JsonValue]],
    ) -> None:
        self.calls += 1
        if self.fail:
            raise ConnectionError("Synthetic graph outage")
        self.claims[job_id] = claims

    def search(
        self, book_id: str, entity_ids: list[str], job_ids: list[str], allowed_passages: list[str]
    ) -> list[str]:
        return list(
            dict.fromkeys(
                p
                for job in job_ids
                for claim in self.claims.get(job, [])
                for p in claim["evidence"]
                if p in allowed_passages
            )
        )


KnowledgeFixture = tuple[
    str, Callable[..., tuple[str, str]], KnowledgeProcessor, Graph, list[list[SourcePassage]]
]


@pytest.fixture
def knowledge(
    client: TestClient, database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> KnowledgeFixture:
    config = client.app.runtime.config
    config.knowledge_enabled = True
    graph = Graph()
    calls = []

    async def extract(sources: list[SourcePassage], config: Settings) -> tuple[ExtractedKnowledge, Metrics]:
        calls.append(sources)
        left = next(s for s in sources if s.side == "left")
        right = next(s for s in sources if s.side == "right")
        name = "Helenka" if "Helenka" in left.text else "the Czech coach"
        return ExtractedKnowledge(
            mentions=[
                ExtractedMention(
                    local_id="coach",
                    passage_id=left.id,
                    surface=name,
                    kind="person",
                    description="Coach of the Czech team in this tournament",
                    named=name == "Helenka",
                ),
                ExtractedMention(
                    local_id="team",
                    passage_id=right.id,
                    surface="Czech team",
                    kind="team",
                    description="Team in the tournament",
                    named=True,
                ),
            ],
            claims=[
                ExtractedClaim(
                    subject="coach",
                    object="team",
                    relation="COACHES",
                    description="The coach leads the team during this tournament.",
                    passage_ids=[left.id, right.id],
                )
            ],
        ), {"input_tokens": 10, "output_tokens": 20, "estimated_cost": 0.001}

    async def resolve(payload: str, config: Settings) -> tuple[Resolutions, Metrics]:
        data = json.loads(payload)
        helenka = next((c for c in data["candidates"] if c["name"] == "Helenka"), None)
        evidence = next((s for s in data["passages"] if "Helenka" in s["text"]), None)
        decisions = []
        for mention in data["mentions"]:
            if mention["text"] == "the Czech coach" and helenka and evidence:
                decisions.append(
                    ResolutionDecision(
                        mention_id=mention["id"],
                        entity_id=helenka["id"],
                        evidence_ids=[mention["passage_id"], evidence["id"]],
                    )
                )
        return Resolutions(decisions=decisions), {
            "input_tokens": 5,
            "output_tokens": 5,
            "estimated_cost": 0.0001,
        }

    monkeypatch.setattr(extraction, "extract", extract)
    monkeypatch.setattr(extraction, "resolve", resolve)
    monkeypatch.setattr(retrieval, "embedder", lambda name: Encoder())
    processor = KnowledgeProcessor(database, config, Encoder(), graph)
    book = client.post("/api/books", json={"title": "Synthetic coaches"}).json()["id"]

    def upload(
        label: str = "1–2", left: str = "Helenka is the coach.", right: str = "The Czech team won."
    ) -> tuple[str, str]:
        with database() as db:
            reading = ReadingSession(
                book_id=book,
                page_label=label,
                image_path="synthetic",
                extraction={"left": left, "right": right, "readable": True},
            )
            db.add(reading)
            db.flush()
            job = KnowledgeRepository(db).enqueue(reading, config.embedding_model)
            db.commit()
            return reading.id, job.id

    return book, upload, processor, graph, calls


def test_passages_preserve_source_offsets_and_hash_ignores_learning_revision(
    database: sessionmaker[Session], client: TestClient
) -> None:
    text = "Helenka spoke to the players. They listened carefully.\n\n" * 120
    values = chunks(text)
    assert len(values) > 1
    assert all(text[start:end] == chunk for start, end, chunk in values)
    reading = ReadingSession(
        page_label="1–2", extraction={"left": text, "right": "More text", "readable": True}, revision=1
    )
    digest = content_hash(reading)
    reading.revision = 8
    assert content_hash(reading) == digest
    reading.extraction = {"left": "Corrected", "right": "More text", "readable": True}
    assert content_hash(reading) != digest


async def test_incremental_resolution_and_cached_graph_retry(
    knowledge: KnowledgeFixture, database: sessionmaker[Session]
) -> None:
    book, upload, processor, graph, calls = knowledge
    _, first = upload()
    await processor.run(first)
    _, second = upload(
        "6–7",
        "Later, the Czech coach declined the proposal.",
        "The Czech team prepared for the same tournament.",
    )
    graph.fail = True
    with pytest.raises(ConnectionError):
        await processor.run(second)
    graph.fail = False
    await processor.run(second)
    await processor.run(second)
    assert len(calls) == 2  # No repeated paid extraction on sync retry.
    with database() as db:
        coach = db.scalar(
            select(Mention).where(Mention.job_id == second, Mention.surface == "the Czech coach")
        )
        entity = db.get(KnowledgeEntity, coach.entity_id)
        assert entity.name == "Helenka" and coach.resolution == "inferred"
        assert len(coach.evidence) == 2
        assert db.get(IndexJob, second).status == "ready"
        assert db.get(IndexJob, second).input_tokens == 15


async def test_ambiguity_stays_unresolved(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, upload, processor, _, _ = knowledge

    async def abstain(payload: str, config: Settings) -> tuple[Resolutions, Metrics]:
        return Resolutions(decisions=[]), {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0}

    monkeypatch.setattr(extraction, "resolve", abstain)
    _, job_id = upload("6–7", "The Czech coach declined.", "The Czech team played.")
    await processor.run(job_id)
    with database() as db:
        mention = db.scalar(
            select(Mention).where(Mention.job_id == job_id, Mention.surface == "the Czech coach")
        )
        assert mention.entity_id is None and mention.resolution == "unresolved"


async def test_later_name_can_resolve_an_earlier_description(
    knowledge: KnowledgeFixture, database: sessionmaker[Session]
) -> None:
    _, upload, processor, _, _ = knowledge
    _, early = upload("1–2", "The Czech coach declined.", "The Czech team played.")
    await processor.run(early)
    _, later = upload("6–7", "Helenka is the coach in the same tournament.", "The Czech team trained.")
    await processor.run(later)
    with database() as db:
        mention = db.scalar(
            select(Mention).where(Mention.job_id == early, Mention.surface == "the Czech coach")
        )
        assert mention.entity_id is not None and mention.resolution == "inferred"
        assert db.get(IndexJob, early).status == "pending"  # durable graph resynchronization


async def test_unnamed_topics_get_nodes_without_identifying_unnamed_people(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, upload, processor, graph, _ = knowledge
    original = extraction.extract

    async def with_topic(
        sources: list[SourcePassage], config: Settings
    ) -> tuple[ExtractedKnowledge, Metrics]:
        result, metrics = await original(sources, config)
        right = next(s for s in sources if s.side == "right")
        result.mentions.append(
            ExtractedMention(
                local_id="topic",
                passage_id=right.id,
                surface="conflict",
                kind="topic",
                description="Conflict discussed by this team",
                named=False,
            )
        )
        result.claims.append(
            ExtractedClaim(
                subject="team",
                object="topic",
                relation="DISCUSSES",
                description="The team discusses conflict.",
                passage_ids=[right.id],
            )
        )
        return result, metrics

    monkeypatch.setattr(extraction, "extract", with_topic)
    _, job = upload("1–2", "The Czech coach spoke.", "The Czech team discussed conflict.")
    await processor.run(job)
    with database() as db:
        topic = db.scalar(select(Mention).where(Mention.job_id == job, Mention.kind == "topic"))
        coach = db.scalar(select(Mention).where(Mention.job_id == job, Mention.kind == "person"))
        assert topic.entity_id is not None and topic.resolution == "explicit"
        assert coach.entity_id is None
        assert any(c["relation"] == "DISCUSSES" for c in graph.claims[job])


async def test_manual_unresolved_survives_later_identity_resolution(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], client: TestClient
) -> None:
    book, upload, processor, _, _ = knowledge
    _, job = upload("1–2", "The Czech coach declined.", "The Czech team played.")
    await processor.run(job)
    mention = client.get(f"/api/books/{book}/knowledge/mentions").json()[0]
    response = client.patch(f"/api/books/{book}/knowledge/mentions/{mention['id']}", json={"entity_id": None})
    assert response.status_code == 200 and response.json()["resolution"] == "reviewed"
    _, later = upload("6–7", "Helenka coaches the Czech team.", "The Czech team trained.")
    await processor.run(later)
    with database() as db:
        saved = db.get(Mention, mention["id"])
        assert saved.entity_id is None and saved.resolution == "reviewed"


async def test_manual_link_keeps_identity_support_for_page_scope(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], client: TestClient
) -> None:
    book, upload, processor, _, _ = knowledge
    _, first = upload()
    await processor.run(first)
    _, second = upload("6–7", "The Czech coach declined.", "The Czech team played.")
    await processor.run(second)
    with database() as db:
        source = db.scalar(select(Mention).where(Mention.job_id == first, Mention.surface == "Helenka"))
        target = db.scalar(select(Mention).where(Mention.job_id == second, Mention.kind == "person"))
        source_id, target_id, entity_id = source.passage_id, target.id, source.entity_id
    response = client.patch(
        f"/api/books/{book}/knowledge/mentions/{target_id}", json={"entity_id": entity_id}
    )
    assert response.status_code == 200
    with database() as db:
        assert source_id in db.get(Mention, target_id).evidence


async def test_summary_hierarchy_is_cached_and_covers_requested_pages(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.knowledge import summaries
    from backend.app.modules.knowledge.models import KnowledgeSummary
    from backend.app.modules.knowledge.schemas import SectionText

    book, upload, processor, _, _ = knowledge
    for first in range(1, 25, 2):
        _, job_id = upload(f"{first}–{first + 1}")
        with database() as db:
            repo = KnowledgeRepository(db)
            job = repo.job(job_id)
            repo.prepare(job)
            for side in ("left", "right"):
                db.add(
                    KnowledgeSummary(job_id=job_id, side=side, text="A generated summary of this page. " * 30)
                )
            db.commit()
    calls = []

    async def summarize(*args: object, **kwargs: object) -> tuple[SectionText, Metrics]:
        calls.append(args)
        return SectionText(text="The coach and players prepare for the tournament."), {
            "input_tokens": 1,
            "output_tokens": 1,
            "estimated_cost": 0,
        }

    monkeypatch.setattr(summaries, "request", summarize)
    await summaries.build(database, processor.config, book, job_id)
    count = len(calls)
    await summaries.build(database, processor.config, book, job_id)
    assert count > 0 and len(calls) == count
    with database() as db:
        repo = KnowledgeRepository(db)
        selected = summaries.select_summaries(repo, book, None, None, 150)
        originals = {p.id for p, _, _ in repo.sources(book)}
        assert selected and all(s.kind == "summary" for s in selected)
        assert {pid for s in selected for pid in s.original_source_ids} == originals
    config = processor.config.model_copy(update={"knowledge_evidence_tokens": 150})
    result = await retrieval.retrieve(
        database, config, book, "Give a recap of the uploaded pages", [], {}, Encoder(), Graph()
    )
    assert result.sources and all(s.kind == "summary" for s in result.sources)
    assert result.notes


async def test_corrections_invalidate_old_sources_and_preserve_history(
    knowledge: KnowledgeFixture, database: sessionmaker[Session]
) -> None:
    book, upload, processor, _, _ = knowledge
    reading_id, old_job = upload()
    await processor.run(old_job)
    with database() as db:
        reading = db.get(ReadingSession, reading_id)
        reading.extraction = {
            "left": "The Czech coach declined.",
            "right": "The Czech team played.",
            "readable": True,
        }
        reading.revision += 1
        new_job = KnowledgeRepository(db).enqueue(reading, processor.config.embedding_model)
        db.commit()
        assert new_job.id != old_job
        assert all(j.id != old_job for j in KnowledgeRepository(db).jobs(book))
        assert db.get(IndexJob, old_job) is not None
        assert not KnowledgeRepository(db).sources(book)
    with pytest.raises(Exception, match="replaced"):
        await processor.run(old_job)


async def test_optional_recap_failure_preserves_graph_and_reports_warning(
    knowledge: KnowledgeFixture,
    database: sessionmaker[Session],
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.ai.client import OutputValidationError
    from backend.app.knowledge import summaries

    book, upload, processor, graph, _ = knowledge
    _, job_id = upload()
    calls = []

    async def unavailable(*args: object, **kwargs: object) -> None:
        calls.append(True)
        raise OutputValidationError(
            "Synthetic truncated section recap",
            {"input_tokens": 7, "output_tokens": 11, "estimated_cost": 0.0001},
        )

    monkeypatch.setattr(summaries, "build", unavailable)
    await processor.run(job_id)
    await processor.run(job_id)
    with database() as db:
        job = db.get(IndexJob, job_id)
        assert job.status == "ready" and job.error is None
        assert "section recap" in job.stages["summary_warning"]
        assert job.input_tokens == 17 and job.output_tokens == 31
    assert len(calls) == 1 and graph.calls == 1
    assert graph.claims[job_id]
    status = client.get(f"/api/books/{book}/knowledge").json()
    assert status["jobs"][0]["status"] == "ready" and status["jobs"][0]["warning"]


async def test_page_route_scope_and_graph_fallback_are_book_scoped(
    knowledge: KnowledgeFixture, database: sessionmaker[Session], client: TestClient
) -> None:
    book, upload, processor, graph, _ = knowledge
    _, job = upload("14–15", "Helenka declined because the players needed rest.", "The Czech team won.")
    await processor.run(job)
    other = client.post("/api/books", json={"title": "Other book"}).json()["id"]
    with database() as db:
        reading = ReadingSession(
            book_id=other,
            page_label="14–15",
            image_path="other",
            extraction={"left": "SECRET OTHER BOOK", "right": "SECRET", "readable": True},
        )
        db.add(reading)
        db.flush()
        new = KnowledgeRepository(db).enqueue(reading, processor.config.embedding_model)
        KnowledgeRepository(db).prepare(new)
        db.commit()
    result = await retrieval.retrieve(
        database, processor.config, book, "Summarize page 14", [], {}, Encoder(), graph
    )
    assert result.plan.strategy == "page" and result.sources
    assert all(s.page_number == 14 and "SECRET" not in s.text for s in result.sources)
    result = await retrieval.retrieve(
        database, processor.config, book, "How are the coach and team related?", [], {}, Encoder(), graph
    )
    assert result.plan.strategy == "relationships" and result.sources
    assert all("SECRET" not in s.text for s in result.sources)
    result = await retrieval.retrieve(
        database, processor.config, book, "Summarize page 14", [], {"page_start": 16}, Encoder(), graph
    )
    assert not result.sources and result.clarification


async def test_english_chat_saves_strategy_and_immutable_evidence(
    knowledge: KnowledgeFixture,
    database: sessionmaker[Session],
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book, upload, processor, _, _ = knowledge
    _, job = upload("14–15")
    await processor.run(job)

    async def answer(
        question: str,
        sources: list[SourcePassage],
        history: list[JsonValue],
        title: str,
        language: str,
        **kwargs: object,
    ) -> tuple[BookAnswer, Metrics]:
        assert language == "en"
        source = sources[0]
        return BookAnswer(
            answer="Helenka is the coach.",
            supported=True,
            citations=[AnswerCitation(source_id=source.id, quote=source.text)],
        ), {"input_tokens": 10, "output_tokens": 10, "estimated_cost": 0.001}

    monkeypatch.setattr(chat, "answer_book", answer)
    thread = client.post(f"/api/books/{book}/chats", json={"language": "cs"}).json()
    assert thread["language"] == "en"
    turn = client.post(
        f"/api/chats/{thread['id']}/messages",
        json={"request_id": str(uuid4()), "question": "Summarize page 14"},
    ).json()
    from backend.app.modules.chat.processing import ChatProcessor

    await ChatProcessor(database, processor.config).generate(turn["id"])
    actual = client.get(f"/api/chats/{thread['id']}").json()["turns"][0]
    assert actual["status"] == "complete" and actual["retrieval_strategy"] == "page"
    assert actual["sources"][0]["page_number"] == 14


def test_status_review_and_backfill_require_owner(knowledge: KnowledgeFixture, client: TestClient) -> None:
    book, upload, _, _, _ = knowledge
    upload()
    assert client.get(f"/api/books/{book}/knowledge").status_code == 200
    assert client.post(f"/api/books/{book}/knowledge/index").status_code == 202
    assert client.get("/api/books/missing/knowledge").status_code == 404


@pytest.mark.skipif(os.environ.get("GRAPH_TESTS") != "1", reason="Opt-in local Neo4j; synthetic data only")
def test_real_graph_roundtrip_filters_stale_jobs_and_out_of_scope_evidence() -> None:
    from backend.app.core.config import Settings

    book, other = str(uuid4()), str(uuid4())
    config = Settings.model_construct(neo4j_password=SecretStr("margin_graph_dev"))
    entities = [
        {"id": str(uuid4()), "name": "Helenka", "kind": "person"},
        {"id": str(uuid4()), "name": "Team", "kind": "team"},
    ]
    claims = [
        {
            "id": str(uuid4()),
            "subject": entities[0]["id"],
            "object": entities[1]["id"],
            "relation": "COACHES",
            "description": "Test relationship",
            "evidence": ["p1", "p2"],
        }
    ]
    try:
        Neo4jStore(config).sync(book, "job1", entities, claims)
        assert set(Neo4jStore(config).search(book, [entities[0]["id"]], ["job1"], ["p1", "p2"])) == {
            "p1",
            "p2",
        }
        assert Neo4jStore(config).search(other, [entities[0]["id"]], ["job1"], ["p1", "p2"]) == []
        assert Neo4jStore(config).search(book, [entities[0]["id"]], ["obsolete"], ["p1", "p2"]) == []
        assert Neo4jStore(config).search(book, [entities[0]["id"]], ["job1"], ["p1"]) == []
        Neo4jStore(config).sync(book, "job1", entities, claims)
        assert set(Neo4jStore(config).search(book, [entities[0]["id"]], ["job1"], ["p1", "p2"])) == {
            "p1",
            "p2",
        }
    finally:
        store = Neo4jStore(config)
        store.driver.execute_query("MATCH (n) WHERE n.book_id=$book DETACH DELETE n", book=book)
        store.driver.close()


@pytest.mark.skipif(
    os.environ.get("TEMPORAL_TESTS") != "1",
    reason="Opt-in local Temporal; synthetic sources and mocked providers",
)
async def test_real_book_index_queue_and_history_replay(
    knowledge: KnowledgeFixture, database: sessionmaker[Session]
) -> None:
    import asyncio
    from datetime import timedelta

    from temporalio.client import Client
    from temporalio.worker import Replayer, Worker

    from backend.app.temporal.knowledge_workflow import IndexBook

    _, upload, processor, graph, _ = knowledge
    _, first = upload()
    _, second = upload("3–4", "The Czech coach declined.", "The Czech team played.")
    temporal = await Client.connect("127.0.0.1:7323")
    queue = "knowledge-test-" + str(uuid4())
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[IndexBook],
        activities=[processor.index_activity, processor.fail_activity],
    ):
        handle = await temporal.start_workflow(
            IndexBook.run,
            args=[[first], 1.0],
            id=queue,
            task_queue=queue,
            execution_timeout=timedelta(seconds=30),
        )
        await handle.signal(IndexBook.enqueue, second)
        for _ in range(150):
            with database() as db:
                done = all(db.get(IndexJob, job_id).status == "ready" for job_id in (first, second))
            if done:
                break
            await asyncio.sleep(0.1)
        assert done
        assert (await handle.result())["processed"] == 2
        history = await handle.fetch_history()
    await Replayer(workflows=[IndexBook]).replay_workflow(history)
