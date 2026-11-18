import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from sqlalchemy import func, select
from temporalio.exceptions import ActivityError, ApplicationError

from backend.app.ai import client as ai
from backend.app.ai.schemas import Learning
from backend.app.modules.conversation.models import ConversationExpression, ConversationSet
from backend.app.modules.conversation.processing import ConversationProcessor
from backend.app.modules.conversation.schemas import GeneratedConversation
from backend.app.modules.readings.models import ReadingSession, StepResult
from backend.app.sample import LEARNING
from backend.app.temporal import workflows


def generated_payload():
    example = {"example_en": "I'm looking forward to meeting you.", "example_cs": "Těším se na setkání s tebou."}
    return {"cards": [{
        "source_index": 1, "meaning_cs": "těšit se na", "explanation_cs": "Vyjadřuje radost z budoucí události.",
        "pattern_cs": "look forward to + podstatné jméno nebo -ing", "register_cs": "Běžná zdvořilá fráze.",
        "work": example, "social": example, "errands": example,
    }]}


def uploaded_reading(client, database):
    sample = client.post("/api/sample").json()
    with database() as db:
        reading = db.get(ReadingSession, sample["session_id"])
        reading.image_path = "test-upload.jpg"
        db.commit()
    return sample["session_id"]


def test_generation_is_explicit_idempotent_and_revision_scoped(client, database):
    reading_id = uploaded_reading(client, database)
    url = f"/api/sessions/{reading_id}/conversation"
    assert client.get(f"/api/books/{client.post('/api/sample').json()['book_id']}/sessions").json()[0]["conversation"] is None
    assert client.post(url, json={"revision": 99}).status_code == 409
    assert client.post(url, json={"revision": 1}).json()["status"] == "pending"
    assert client.post(url, json={"revision": 1}).status_code == 202
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ConversationSet)) == 1
        assert db.get(ReadingSession, reading_id).status == "complete"


async def test_activity_stores_exact_source_and_reuses_result(client, database, monkeypatch):
    reading_id = uploaded_reading(client, database)
    config = client.app.runtime.config
    calls = []

    async def generate(*args, **kwargs):
        calls.append(1)
        return GeneratedConversation.model_validate(generated_payload()), {"input_tokens": 10, "output_tokens": 20, "estimated_cost": .001}

    monkeypatch.setattr(ai, "conversation", generate)
    processor = ConversationProcessor(database, config)
    job = {"session_id": reading_id, "revision": 1}
    await processor.generate(job)
    await processor.generate(job)
    assert len(calls) == 1
    with database() as db:
        item = db.scalar(select(ConversationSet))
        card = db.scalar(select(ConversationExpression))
        assert item.status == "complete"
        assert card.payload["expression"] == LEARNING["expressions"][1]["expression"]
        assert card.payload["source_sentence"] == LEARNING["expressions"][1]["source_sentence"]
        assert db.scalar(select(func.count()).select_from(StepResult)) == 1
    response = client.post(f"/api/sessions/{reading_id}/conversation", json={"revision": 1}).json()
    assert response["status"] == "complete" and len(response["cards"]) == 1
    processor.fail({**job, "message": "Late failure must not overwrite success"})
    with database() as db:
        assert db.scalar(select(ConversationSet)).status == "complete"


async def test_stale_activity_cannot_save_examples(client, database, monkeypatch):
    reading_id = uploaded_reading(client, database)

    async def generate(*args, **kwargs):
        with database() as db:
            db.get(ReadingSession, reading_id).revision += 1
            db.commit()
        return GeneratedConversation.model_validate(generated_payload()), {"input_tokens": 1, "output_tokens": 1, "estimated_cost": .001}

    monkeypatch.setattr(ai, "conversation", generate)
    with pytest.raises(ApplicationError, match="newer revision"):
        await ConversationProcessor(database, client.app.runtime.config).generate({"session_id": reading_id, "revision": 1})
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ConversationExpression)) == 0


def test_every_conversational_context_is_required():
    payload = generated_payload()
    del payload["cards"][0]["errands"]
    with pytest.raises(ValidationError):
        GeneratedConversation.model_validate(payload)


async def test_selection_must_refer_to_distinct_source_expressions(database, monkeypatch):
    async def request(*args, **kwargs):
        payload = generated_payload()
        payload["cards"][0]["source_index"] = 21
        return GeneratedConversation.model_validate(payload), {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0}

    monkeypatch.setattr(ai, "request", request)
    with pytest.raises(UnexpectedModelBehavior, match="supplied expressions"):
        await ai.conversation(Learning.model_validate(LEARNING), config=ai.settings())


@pytest.mark.parametrize("version,expected", [
    (None, ["extract_pages", "translate_pages", "create_learning", "finish_reading"]),
    (2, ["extract_pages", "create_learning", "finish_reading"]),
    (3, ["extract_pages", "create_learning", "create_conversation", "finish_reading"]),
])
async def test_pipeline_versions_keep_their_command_order(monkeypatch, version, expected):
    seen = []

    async def activity(name, *args, **kwargs):
        seen.append(name)

    monkeypatch.setattr(workflows.workflow, "execute_activity", activity)
    job = {"session_id": "test", "revision": 1}
    if version:
        job["pipeline_version"] = version
    await workflows.ReadSpread().run(job)
    assert seen == expected


async def test_conversation_failure_does_not_fail_reading(monkeypatch):
    seen = []

    async def activity(name, *args, **kwargs):
        seen.append(name)
        if name == "create_conversation":
            raise ActivityError("failed", scheduled_event_id=1, started_event_id=2, identity="test", activity_type=name, activity_id="1", retry_state=None) from ApplicationError("Provider unavailable")

    monkeypatch.setattr(workflows.workflow, "execute_activity", activity)
    await workflows.ReadSpread().run({"session_id": "test", "revision": 1, "pipeline_version": 3})
    assert seen[-2:] == ["fail_conversation", "finish_reading"]
