from urllib.parse import urlparse

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.ai.schemas import GeneratedLearning, Learning
from backend.app.core import body_limits
from backend.app.modules.capture import service
from backend.app.modules.capture.models import Pairing
from backend.app.modules.capture.repository import CaptureRepository
from backend.app.modules.readings.models import ReadingSession
from backend.app.sample import LEARNING


def batch_link(client):
    book = client.post("/api/books", json={"title": "A batch book"}).json()
    pairing = client.post(f"/api/books/{book['id']}/pair").json()
    token = urlparse(pairing["url"]).path.split("/")[-1]
    return book["id"], token


def batch_request(client, token, images, labels):
    return client.post(f"/api/capture/{token}/batch", files=[("images", (f"photo-{index}.jpg", image, "image/jpeg")) for index, image in enumerate(images)], data={"page_labels": labels})


def test_batch_creates_one_ordered_pending_reading_per_photo(client, database, photo):
    book_id, token = batch_link(client)
    labels = [f"{12 + index * 2}–{13 + index * 2}" for index in range(6)]
    response = batch_request(client, token, [photo] * 6, labels)
    assert response.status_code == 201, response.text
    batch = response.json()
    assert len(set(batch["session_ids"])) == 6
    readings = client.get(f"/api/books/{book_id}/sessions").json()
    assert [reading["page_label"] for reading in readings] == labels
    assert [reading["batch_position"] for reading in readings] == list(range(6))
    assert all(reading["batch_id"] == batch["batch_id"] and reading["status"] == "pending" for reading in readings)
    with database() as db:
        rows = db.scalars(select(ReadingSession)).all()
        assert all(row.context == rows[0].context for row in rows)
        assert db.scalar(select(Pairing)).used
    assert batch_request(client, token, [photo], ["30–31"]).status_code == 409
    assert len(list(client.app.runtime.config.data_dir.glob("uploads/*.jpg"))) == 6


@pytest.mark.parametrize("count,labels", [(11, ["pages"] * 11), (2, ["only one label"]), (1, ["x" * 101])])
def test_batch_rejects_invalid_count_or_labels(client, database, photo, count, labels):
    _, token = batch_link(client)
    assert batch_request(client, token, [photo] * count, labels).status_code == 422
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReadingSession)) == 0
        assert not db.scalar(select(Pairing)).used


def test_bad_second_photo_rolls_back_all_rows_and_files(client, database, photo):
    _, token = batch_link(client)
    assert batch_request(client, token, [photo, b"invalid image"], ["12–13", "14–15"]).status_code == 422
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReadingSession)) == 0
        assert not db.scalar(select(Pairing)).used
    assert not list(client.app.runtime.config.data_dir.glob("uploads/*.jpg"))
    assert batch_request(client, token, [photo], ["12–13"]).status_code == 201


def test_failed_atomic_claim_removes_entire_batch(client, database, photo, monkeypatch):
    _, token = batch_link(client)
    monkeypatch.setattr(CaptureRepository, "claim", lambda *args: False)
    assert batch_request(client, token, [photo] * 2, ["12–13", "14–15"]).status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReadingSession)) == 0
    assert not list(client.app.runtime.config.data_dir.glob("uploads/*.jpg"))


def test_total_batch_size_is_bounded_and_rolls_back(client, database, photo, monkeypatch):
    _, token = batch_link(client)
    monkeypatch.setattr(service, "MAX_BATCH_BYTES", len(photo) + 1)
    assert batch_request(client, token, [photo] * 2, ["12–13", "14–15"]).status_code == 413
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReadingSession)) == 0
    assert not list(client.app.runtime.config.data_dir.glob("uploads/*.jpg"))


def test_streaming_body_cap_prevents_parsing_oversized_batch(client, database, photo, monkeypatch):
    _, token = batch_link(client)
    monkeypatch.setattr(body_limits, "MAX_BATCH_REQUEST_BYTES", 100)
    response = batch_request(client, token, [photo], ["12–13"])
    assert response.status_code == 413, response.text


def test_each_photo_has_its_own_size_limit(client, database, photo, monkeypatch):
    _, token = batch_link(client)
    monkeypatch.setattr(service, "MAX_IMAGE_BYTES", len(photo) - 1)
    assert batch_request(client, token, [photo], ["12–13"]).status_code == 413
    with database() as db:
        assert not db.scalar(select(Pairing)).used


async def test_body_cap_closes_already_spooled_files(client, database, photo, monkeypatch):
    from tempfile import SpooledTemporaryFile

    files = []

    def tracked_file(*args, **kwargs):
        file = SpooledTemporaryFile(*args, **kwargs)
        files.append(file)
        return file

    import starlette.formparsers as parser
    monkeypatch.setattr(parser, "SpooledTemporaryFile", tracked_file)
    monkeypatch.setattr(body_limits, "MAX_BATCH_REQUEST_BYTES", 500)
    from backend.app.core.body_limits import BatchBodyLimitMiddleware
    from starlette.responses import Response

    boundary = "test-boundary"
    header = f'--{boundary}\r\nContent-Disposition: form-data; name="images"; filename="one.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
    chunks = iter([header + b"a" * 100, b"b" * 600])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def app(scope, receive, send):
        from starlette.requests import Request
        request = Request(scope, receive)
        # Request.form handles the parser's MultiPartException and closes partial files.
        try:
            await request.form()
        except Exception:
            pass
        await Response(status_code=400)(scope, receive, send)

    messages = []
    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/capture/token/batch", "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())]}
    await BatchBodyLimitMiddleware(app)(scope, receive, send)
    assert messages[0]["status"] == 413
    assert files and all(file.closed for file in files)


def test_topic_title_required_for_new_outputs_optional_for_old_readings():
    payload = {**LEARNING, "expressions": LEARNING["expressions"] * 2}
    assert GeneratedLearning.model_validate(payload).topic_title
    del payload["topic_title"]
    assert Learning.model_validate(payload).topic_title is None
    with pytest.raises(ValidationError, match="topic title"):
        GeneratedLearning.model_validate(payload)
