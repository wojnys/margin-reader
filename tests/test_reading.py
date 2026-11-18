import hashlib
from datetime import timedelta
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app import main
from backend.app.modules.readings import processing
from backend.app.ai.client import validate_grounding
from backend.app.db.models import Pairing, ReadingSession, Review, StepResult, Vocabulary
from backend.app.db.base import now
from backend.app.sample import LEARNING, LEFT, RIGHT
from backend.app.ai.schemas import ExtractedPages, GeneratedLearning, Learning


def add_book(client):
    response = client.post(
        "/api/books", json={"title": "A test book", "author": "Test author", "level": "B2"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_admin_is_not_available_to_unpaired_phone(database):
    local = TestClient(main.app, base_url="http://localhost", client=("127.0.0.1", 3))
    assert local.get("/api/books").status_code == 401
    assert local.post("/api/bootstrap", headers={"Origin": "https://untrusted.example"}).status_code == 403
    phone = TestClient(main.app, base_url="http://192.168.1.3", client=("192.168.1.9", 3))
    assert phone.post("/api/bootstrap").status_code == 403
    assert phone.get("/api/books").status_code == 401
    forged_host = TestClient(main.app, base_url="http://localhost", client=("192.168.1.9", 3))
    assert forged_host.post("/api/bootstrap").status_code == 403


def test_upload_validation_and_single_use_pairing(client, database, photo):
    book_id = add_book(client)
    assert (
        client.post(
            f"/api/books/{book_id}/sessions", files={"image": ("fake.jpg", b"not an image")}
        ).status_code
        == 422
    )
    pair = client.post(f"/api/books/{book_id}/pair").json()
    token = urlparse(pair["url"]).path.split("/")[-1]
    phone = TestClient(main.app, base_url="http://192.168.1.3")
    assert phone.get(f"/api/capture/{token}").json()["book_title"] == "A test book"
    assert (
        phone.post(
            f"/api/capture/{token}", files={"image": ("pages.jpg", photo)}, data={"page_label": "10–11"}
        ).status_code
        == 201
    )
    assert phone.post(f"/api/capture/{token}", files={"image": ("pages.jpg", photo)}).status_code == 409
    readings = client.get(f"/api/books/{book_id}/sessions").json()
    assert len(readings) == 1 and readings[0]["status"] == "pending"
    with database() as db:
        pairing = db.get(Pairing, hashlib.sha256(token.encode()).hexdigest())
        pairing.expires_at = now() - timedelta(minutes=1)
        db.commit()
    assert phone.get(f"/api/capture/{token}").status_code == 410


def test_vocabulary_deduplication_review_and_due_dates(client, database):
    sample = client.post("/api/sample").json()
    payload = {"session_id": sample["session_id"], "revision": 1, "index": 0}
    first = client.post("/api/vocabulary", json=payload).json()
    second = client.post("/api/vocabulary", json=payload).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/vocabulary?due=true").json()) == 1
    review = {"id": str(uuid4()), "rating": 2}
    assert client.post(f"/api/vocabulary/{first['id']}/reviews", json=review).status_code == 200
    client.post(f"/api/vocabulary/{first['id']}/reviews", json=review)
    assert not client.get("/api/vocabulary?due=true").json()
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1
        assert db.get(Vocabulary, first["id"]).repetitions == 1


def test_correction_invalidates_outputs_and_rejects_stale_save(client, database):
    sample = client.post("/api/sample").json()
    response = client.put(
        f"/api/sessions/{sample['session_id']}/text",
        json={"revision": 1, "left": "Correct left.", "right": "Correct right."},
    )
    assert response.status_code == 200
    reading = response.json()
    assert reading["revision"] == 2 and reading["status"] == "pending"
    assert reading["translation"] is None and reading["learning"] is None
    assert (
        client.post(
            "/api/vocabulary", json={"session_id": reading["id"], "revision": 1, "index": 0}
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/sessions/{reading['id']}/text", json={"revision": 1, "left": "old", "right": "old"}
        ).status_code
        == 409
    )


async def test_successful_stages_are_reused_on_retry(client, database, photo, monkeypatch):
    book_id = add_book(client)
    reading = client.post(f"/api/books/{book_id}/sessions", files={"image": ("pages.jpg", photo)}).json()
    job = {"session_id": reading["id"], "revision": 1}
    calls = []

    def extract(_):
        calls.append("extract")
        return ExtractedPages(left=LEFT, right=RIGHT, readable=True)

    async def teach(*_, **kwargs):
        calls.append("teach")
        return Learning.model_validate(LEARNING), {
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost": 0.001,
        }

    monkeypatch.setattr(processing, "extract_pages", extract)
    monkeypatch.setattr(processing.ai, "teach", teach)
    await processing.process_stage(job, "extract")
    await processing.process_stage(job, "teach")
    await processing.process_stage(job, "extract")
    await processing.process_stage(job, "teach")
    assert calls == ["extract", "teach"]
    with database() as db:
        steps = db.scalars(select(StepResult).order_by(StepResult.stage)).all()
        assert len(steps) == 2
        assert steps[0].model == "local-rapidocr" and steps[0].estimated_cost == 0
        session = db.get(ReadingSession, job["session_id"])
        session.revision = 2
        db.commit()
    with pytest.raises(Exception, match="newer revision"):
        await processing.process_stage(job, "extract")


def test_quotations_must_come_from_the_correct_page():
    learning = Learning.model_validate(LEARNING)
    validate_grounding(learning, ExtractedPages(left=LEFT, right=RIGHT, readable=True))
    learning.expressions[3].source_sentence = learning.expressions[3].source_sentence.replace("'", "’")
    validate_grounding(learning, ExtractedPages(left=LEFT, right=RIGHT, readable=True))
    learning.expressions[0].source_sentence = "A quotation the model invented."
    with pytest.raises(ValueError, match="source page"):
        validate_grounding(learning, ExtractedPages(left=LEFT, right=RIGHT, readable=True))


def test_generated_readings_require_ten_to_twenty_two_expressions():
    from pydantic import ValidationError

    payload = {**LEARNING, "expressions": LEARNING["expressions"] * 2}
    assert len(GeneratedLearning.model_validate(payload).expressions) == 10
    with pytest.raises(ValidationError):
        GeneratedLearning.model_validate(LEARNING)
    with pytest.raises(ValidationError):
        GeneratedLearning.model_validate({**LEARNING, "expressions": LEARNING["expressions"] * 5})
    # Readings saved before this change and the prepared sample still load normally.
    assert len(Learning.model_validate(LEARNING).expressions) == 5


def test_all_twenty_two_expressions_can_be_saved(client, database):
    sample = client.post("/api/sample").json()
    with database() as db:
        reading = db.get(ReadingSession, sample["session_id"])
        reading.learning = {
            **LEARNING,
            "expressions": [
                {**LEARNING["expressions"][0], "expression": f"Expression {index + 1}"} for index in range(22)
            ],
        }
        db.commit()
    for index in range(22):
        response = client.post(
            "/api/vocabulary", json={"session_id": sample["session_id"], "revision": 1, "index": index}
        )
        assert response.status_code == 201
        assert response.json()["expression"] == f"Expression {index + 1}"
    assert len(client.get("/api/vocabulary").json()) == 22
    assert (
        client.post(
            "/api/vocabulary", json={"session_id": sample["session_id"], "revision": 1, "index": 22}
        ).status_code
        == 422
    )


def test_refresh_learning_reuses_ocr_text_preserving_saved_vocabulary(client, database):
    sample = client.post("/api/sample").json()
    with database() as db:
        reading = db.get(ReadingSession, sample["session_id"])
        reading.image_path = "uploaded-book.jpg"
        original_text = reading.extraction
        db.add(
            StepResult(
                session_id=reading.id,
                revision=1,
                stage="teach",
                model="test-model",
                result=reading.learning,
                estimated_cost=0.01,
            )
        )
        db.commit()
    saved = client.post(
        "/api/vocabulary", json={"session_id": sample["session_id"], "revision": 1, "index": 0}
    )
    assert saved.status_code == 201
    result = client.post(f"/api/sessions/{sample['session_id']}/learning", json={"revision": 1})
    assert result.status_code == 200
    reading = result.json()
    assert reading["revision"] == 2 and reading["status"] == "pending"
    assert reading["learning"] is None
    assert reading["extraction"]["left"] == original_text["left"]
    assert reading["extraction"]["right"] == original_text["right"]
    assert reading["translation"] is None
    assert reading["usage"]["estimated_cost"] == 0.01
    assert len(client.get("/api/vocabulary").json()) == 1
    assert (
        client.post(f"/api/sessions/{sample['session_id']}/learning", json={"revision": 1}).status_code == 409
    )


async def test_unreadable_output_is_saved_without_repeated_paid_calls(client, database, photo, monkeypatch):
    book_id = add_book(client)
    reading = client.post(f"/api/books/{book_id}/sessions", files={"image": ("pages.jpg", photo)}).json()
    calls = []

    def extract(_):
        calls.append(1)
        return ExtractedPages(left="Partial text", right="", readable=False)

    monkeypatch.setattr(processing, "extract_pages", extract)
    for _ in range(2):
        with pytest.raises(Exception, match="Both pages need to be readable"):
            await processing.process_stage({"session_id": reading["id"], "revision": 1}, "extract")
    assert len(calls) == 1
    with database() as db:
        assert db.get(ReadingSession, reading["id"]).extraction["left"] == "Partial text"
        assert db.scalar(select(func.count()).select_from(StepResult)) == 1


async def test_provider_authentication_failure_is_not_retried(client, database, photo, monkeypatch):
    from pydantic_ai.exceptions import ModelHTTPError
    from temporalio.exceptions import ApplicationError

    book_id = add_book(client)
    reading = client.post(f"/api/books/{book_id}/sessions", files={"image": ("pages.jpg", photo)}).json()

    async def teach(*_, **kwargs):
        raise ModelHTTPError(401, "model", {"error": "Invalid test key"})

    with database() as db:
        session = db.get(ReadingSession, reading["id"])
        session.extraction = ExtractedPages(left=LEFT, right=RIGHT, readable=True).model_dump(mode="json")
        db.commit()
    monkeypatch.setattr(processing.ai, "teach", teach)
    with pytest.raises(ApplicationError) as failure:
        await processing.process_stage({"session_id": reading["id"], "revision": 1}, "teach")
    assert failure.value.non_retryable
    assert "HTTP 401" in failure.value.message
    assert "Invalid test key" in failure.value.message
