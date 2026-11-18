"""Exercise real PydanticAI parsing against mocked HTTP responses, never paid APIs."""

import json
from collections.abc import Awaitable
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai.exceptions import UnexpectedModelBehavior
from sqlalchemy.orm import Session, sessionmaker
from temporalio.exceptions import ApplicationError

from backend.app.ai import client as ai
from backend.app.core.config import Settings
from backend.app.knowledge.extraction import extract, resolve, selected_surface, source_tokens
from backend.app.modules.chat.schemas import SourcePassage
from backend.app.modules.knowledge import processing
from backend.app.modules.knowledge.models import IndexJob
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.readings.models import ReadingSession


def completion(content: str, finish: str = "stop") -> dict[str, object]:
    return {
        "id": "offline-extraction",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-ai/DeepSeek-V4.1-Flash-1017",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
    }


def mock_provider(
    monkeypatch: pytest.MonkeyPatch, replies: list[dict[str, object]]
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=replies[min(len(requests) - 1, len(replies) - 1)])

    def fake_client(**kwargs: object) -> AsyncOpenAI:
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(ai, "AsyncOpenAI", fake_client)
    return requests


def source() -> SourcePassage:
    return SourcePassage(
        id=str(uuid4()),
        session_id=str(uuid4()),
        revision=1,
        page_label="14–15",
        side="left",
        text="Helenka coaches the Czech\nteam.",
    )


def result() -> dict[str, object]:
    return {
        "mentions": [
            {
                "local_id": "M1",
                "passage_id": "P1",
                "start_token": 1,
                "end_token": 1,
                "kind": "person",
                "description": "Coach",
                "named": True,
            },
            {
                "local_id": "M2",
                "passage_id": "P1",
                "start_token": 4,
                "end_token": 5,
                "kind": "team",
                "description": "The coached team",
                "named": True,
            },
        ],
        "claims": [
            {
                "subject": "M1",
                "object": "M2",
                "relation": "COACHES",
                "description": "Helenka coaches the team.",
                "passage_ids": ["P1"],
            }
        ],
    }


@pytest.mark.parametrize(
    "text,start,end,expected",
    [
        ("Czech\n team", 1, 2, "Czech\n team"),
        ("John’s team", 1, 2, "John’s team"),
        ("a long—term goal", 2, 4, "long—term"),
        ("Helenka coaches the team.", 1, 1, "Helenka"),
        ("Helenka coaches the team.", 1, 99, None),
        ("Helenka coaches the team.", 3, 1, None),
    ],
)
def test_surface_restores_exact_source_without_accepting_paraphrases(
    text: str, start: int, end: int, expected: str | None
) -> None:
    assert selected_surface(text, source_tokens(text), start, end) == expected


async def test_extraction_maps_short_labels_to_real_ids_and_restores_ocr_spacing(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    passage = source()
    requests = mock_provider(monkeypatch, [completion(json.dumps(result()))])
    actual, metrics = await extract([passage], ai.settings())
    assert len(requests) == 1
    assert actual.mentions[1].surface == "Czech\nteam"
    assert all(m.passage_id == passage.id for m in actual.mentions)
    assert actual.claims[0].passage_ids == [passage.id]
    assert passage.id not in json.dumps(requests[0]["messages"])
    assert "P1" in json.dumps(requests[0]["messages"])
    assert requests[0]["max_tokens"] == 12000
    assert requests[0]["reasoning_effort"] == "none"
    assert metrics["input_tokens"] == 100


async def test_invalid_passage_label_is_corrected_without_accepting_fabricated_ids(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace('"P1"', '"P999"')
    requests = mock_provider(monkeypatch, [completion(invalid), completion(json.dumps(result()))])
    passage = source()
    actual, metrics = await extract([passage], ai.settings())
    assert len(requests) == 2
    assert actual.mentions[0].passage_id == passage.id
    assert "mentions[0].passage_id" in json.dumps(requests[1]["messages"])
    assert metrics["input_tokens"] == 200


async def test_failed_grounding_retains_safe_detail_and_failed_request_usage(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace('"end_token": 1', '"end_token": 999')
    requests = mock_provider(monkeypatch, [completion(invalid)])
    with pytest.raises(ai.OutputValidationError, match=r"mentions\[0\].token_range") as caught:
        await extract([source()], ai.settings())
    assert isinstance(caught.value, UnexpectedModelBehavior)
    assert len(requests) == 2  # One bounded PydanticAI correction, not unlimited repeats.
    assert caught.value.metrics["input_tokens"] == 200
    assert caught.value.metrics["output_tokens"] == 400
    assert "Invented person" not in str(caught.value)


async def test_schema_error_names_the_bad_field_without_dumping_model_output(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace('"person"', '"malformed-and-private-output"')
    mock_provider(monkeypatch, [completion(invalid)])
    with pytest.raises(ai.OutputValidationError, match=r"mentions.0.kind") as caught:
        await extract([source()], ai.settings())
    assert "malformed-and-private-output" not in str(caught.value)


async def test_freeform_invented_name_is_not_an_accepted_mention_field(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace(
        '"local_id": "M1"', '"surface": "Invented person", "local_id": "M1"'
    )
    mock_provider(monkeypatch, [completion(invalid)])
    with pytest.raises(ai.OutputValidationError, match="Extra inputs are not permitted") as caught:
        await extract([source()], ai.settings())
    assert "Invented person" not in str(caught.value)


async def test_reference_resolution_has_its_own_reasoning_policy(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = ai.settings().model_copy(update={"deepinfra_reasoning_effort": "high"})
    requests = mock_provider(monkeypatch, [completion('{"decisions":[]}')])
    actual, _ = await resolve('{"mentions":[],"candidates":[],"passages":[]}', config)
    assert actual.decisions == []
    assert requests[0]["reasoning_effort"] == "none"


async def test_truncation_has_a_distinct_actionable_error(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_provider(monkeypatch, [completion('{"mentions":[', "length")])
    with pytest.raises(ai.OutputValidationError, match="12000-token limit"):
        await extract([source()], ai.settings())


async def test_truncation_does_not_hide_the_following_validation_failure(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace('"end_token": 1', '"end_token": 999')
    mock_provider(monkeypatch, [completion('{"mentions":[', "length"), completion(invalid)])
    with pytest.raises(ai.OutputValidationError) as caught:
        await extract([source()], ai.settings())
    assert "12000-token limit" in str(caught.value)
    assert "mentions[0].token_range" in str(caught.value)


async def test_final_schema_failure_is_not_replaced_by_earlier_json_feedback(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.dumps(result()).replace('"person"', '"private-invalid-value"')
    mock_provider(monkeypatch, [completion('{"mentions":['), completion(invalid)])
    with pytest.raises(ai.OutputValidationError) as caught:
        await extract([source()], ai.settings())
    assert "mentions.0.kind" in str(caught.value)
    assert "private-invalid-value" not in str(caught.value)


async def test_activity_stops_paid_validation_retries_and_records_usage(
    database: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    config: Settings = ai.settings()
    with database() as db:
        from backend.app.modules.books.models import Book

        book = Book(title="Offline error test")
        db.add(book)
        db.flush()
        reading = ReadingSession(
            book_id=book.id,
            image_path="synthetic",
            page_label="1–2",
            extraction={"left": "Helenka", "right": "Team", "readable": True},
        )
        db.add(reading)
        db.flush()
        job_id = KnowledgeRepository(db).enqueue(reading, config.embedding_model).id
        db.commit()
    processor = processing.KnowledgeProcessor(database, config)

    async def fail(_job_id: str) -> None:
        raise ai.OutputValidationError(
            "mentions.0.kind: unsupported type",
            {"input_tokens": 200, "output_tokens": 400, "estimated_cost": 0.001},
        )

    async def no_heartbeat(awaitable: Awaitable[None]) -> None:
        await awaitable

    monkeypatch.setattr(processor, "run", fail)
    monkeypatch.setattr(processing, "with_heartbeats", no_heartbeat)
    with pytest.raises(ApplicationError, match="mentions.0.kind") as caught:
        await processor.index_activity(job_id)
    assert caught.value.non_retryable
    assert caught.value.type == "KnowledgeOutputValidationError"
    with database() as db:
        job = db.get(IndexJob, job_id)
        assert job.input_tokens == 200 and job.output_tokens == 400
        assert job.estimated_cost == 0.001
