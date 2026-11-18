import asyncio
import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
import httpx
from openai import AsyncOpenAI
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import UnexpectedModelBehavior
from sqlalchemy import select
from temporalio.client import Client
from temporalio.worker import Replayer, Worker

from backend.app import main
from backend.app.ai import chat as ai
from backend.app.ai import client as provider_client
from backend.app.modules.chat.context import select_context
from backend.app.modules.chat.models import ChatThread, ChatTurn
from backend.app.modules.chat.processing import ChatProcessor
from backend.app.modules.chat.schemas import AnswerCitation, BookAnswer, SourcePassage
from backend.app.modules.readings.models import ReadingSession
from backend.app.temporal.chat_workflow import AnswerBookChat


def book_and_chat(client):
    sample = client.post('/api/sample').json()
    thread = client.post(f"/api/books/{sample['book_id']}/chats", json={"language": "cs"}).json()
    return sample, thread


def ask(client, thread, question="What does Anna find?", request_id=None):
    return client.post(f"/api/chats/{thread['id']}/messages", json={"request_id": request_id or str(uuid4()), "question": question})


def test_chats_require_owner_and_valid_book(client):
    with TestClient(main.app) as phone:
        assert phone.get('/api/books/missing/chats').status_code == 401
        assert phone.post('/api/books/missing/chats', json={}).status_code == 401
    assert client.post('/api/books/missing/chats', json={}).status_code == 404
    assert client.get('/api/chats/missing').status_code == 404


def test_saved_threads_language_idempotency_and_active_turn(client, database):
    sample, thread = book_and_chat(client)
    request_id = str(uuid4())
    first = ask(client, thread, request_id=request_id)
    assert first.status_code == 202 and first.json()['status'] == 'pending'
    assert ask(client, thread, request_id=request_id).json()['id'] == first.json()['id']
    assert ask(client, thread, question='Another question', request_id=request_id).status_code == 409
    assert ask(client, thread, question='Another question').status_code == 409
    detail = client.get(f"/api/chats/{thread['id']}").json()
    assert detail['language'] == 'en' and len(detail['turns']) == 1
    assert client.get(f"/api/books/{sample['book_id']}/chats").json()[0]['title'] == 'What does Anna find?'
    with database() as db:
        assert db.get(ChatThread, thread['id']).active_turn_id == first.json()['id']


def test_empty_text_and_unprocessed_books(client):
    book = client.post('/api/books', json={'title': 'No uploaded text'}).json()
    thread = client.post(f"/api/books/{book['id']}/chats", json={}).json()
    assert ask(client, thread).status_code == 409
    assert ask(client, thread, question='   ').status_code == 422


async def test_reply_reads_all_book_spreads_no_other_book_and_keeps_snapshot(client, database, monkeypatch):
    sample, thread = book_and_chat(client)
    other = client.post('/api/books', json={'title': 'Other book'}).json()
    with database() as db:
        db.add(ReadingSession(book_id=sample['book_id'], page_label='50–51', image_path='test', context={}, extraction={"left": "A new political agreement was signed.", "right": "The delegates returned home.", "readable": True}, revision=3))
        db.add(ReadingSession(book_id=other['id'], page_label='90–91', image_path='other', context={}, extraction={"left": "SECRET OTHER BOOK", "right": "PRIVATE", "readable": True}))
        db.commit()
    seen = []

    async def answer(question, sources, history, title, language, **kwargs):
        seen.append(sources)
        assert any(source.page_label == '50–51' and source.revision == 3 for source in sources)
        assert all('SECRET OTHER BOOK' not in source.text for source in sources)
        source = next(source for source in sources if source.page_label == '50–51')
        return BookAnswer(answer="Byla podepsána nová dohoda.", supported=True, citations=[AnswerCitation(source_id=source.id, quote="A new political agreement was signed.")]), {"input_tokens": 20, "output_tokens": 30, "estimated_cost": .001}

    monkeypatch.setattr(ai, 'answer_book', answer)
    turn = ask(client, thread).json()
    processor = ChatProcessor(database, client.app.runtime.config)
    await processor.generate(turn['id'])
    await processor.generate(turn['id'])
    assert len(seen) == 1
    with database() as db:
        reading = db.scalar(select(ReadingSession).where(ReadingSession.page_label == '50–51'))
        reading.extraction = {"left": "Corrected text", "right": "Different text", "readable": True}
        reading.revision += 1
        db.commit()
    detail = client.get(f"/api/chats/{thread['id']}").json()['turns'][0]
    assert detail['status'] == 'complete' and detail['estimated_cost'] == .001
    assert any(source['revision'] == 3 and 'agreement' in source['text'] for source in detail['sources'])
    assert ask(client, thread, question='What happened next?').status_code == 202


def test_citation_validation_rejects_other_sources_and_invented_quotes():
    source = SourcePassage(id='a', session_id='reading', revision=1, page_label='1–2', side='left', text='Anna found a notebook.')
    for supported, citations in [(True, []), (True, [AnswerCitation(source_id='other', quote='Anna')]), (True, [AnswerCitation(source_id='a', quote='Invented event')])]:
        with pytest.raises(UnexpectedModelBehavior):
            ai.validate_answer(BookAnswer(answer='Reply', supported=supported, citations=citations), [source])
    ai.validate_answer(BookAnswer(answer='The pages do not say.', supported=False, citations=[]), [source])


def test_long_books_search_every_passage_and_bound_context():
    sources = [SourcePassage(id=str(i), session_id=str(i), revision=1, page_label=str(i), side='left', text=('Some story. ' * 145) + ('specific penguin treaty' if i == 95 else '')) for i in range(100)]
    chosen = select_context(sources, 'Explain the penguin treaty')
    assert len(chosen) <= 24 and any(source.id == '95' for source in chosen)


async def test_model_selects_short_evidence_labels_and_server_copies_exact_ocr(client, monkeypatch):
    source = SourcePassage(id='long-immutable-reading-id:v3:right:0', session_id='reading', revision=3, page_label='14–15', side='right', text='“You will never be a diplomat,” he said. Working-class people need not apply.')
    requests = []

    def provider(request):
        requests.append(json.loads(request.content))
        # First model attempt supplies an invalid label. PydanticAI must supply feedback
        # and accept the corrected output inside the same activity, without losing context.
        reference = 'not-a-source' if len(requests) == 1 else 'E1'
        return httpx.Response(200, json={
            'id': 'test-chat', 'object': 'chat.completion', 'created': 1, 'model': 'test',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps({
                'answer': 'Kvůli společenským a finančním překážkám.', 'supported': True,
                'citations': [{'evidence_id': reference}],
            })}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
        })

    def fake_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))

    monkeypatch.setattr(provider_client, 'AsyncOpenAI', fake_client)
    answer, metrics = await ai.answer_book('Why was it difficult?', [source], [], 'A book', 'cs', config=client.app.runtime.config)
    assert len(requests) == 2
    assert requests[0]['max_tokens'] == 4096
    assert answer.citations[0].source_id == source.id
    assert answer.citations[0].quote == source.text
    assert metrics['input_tokens'] == 20 and metrics['output_tokens'] == 40
    ai.validate_answer(answer, [source])


def test_evidence_units_cover_original_text_without_inventing_quotes():
    source = SourcePassage(id='a', session_id='s', revision=1, page_label='1', side='left', text='An OCR line with typographic apostrophes ’ and quotes “like this”. ' * 60)
    units = ai.evidence_units([source])
    assert len(units) > 1
    assert all(text in source.text and len(text) <= 600 for _, text in units.values())
    assert ' '.join(text for _, text in units.values()) == source.text.strip()


async def test_failure_unlocks_chat_and_retry_retains_source_snapshot(client, database, monkeypatch):
    _, thread = book_and_chat(client)
    turn = ask(client, thread).json()
    processor = ChatProcessor(database, client.app.runtime.config)

    async def unavailable(*args, **kwargs):
        raise UnexpectedModelBehavior('invalid citation')

    monkeypatch.setattr(ai, 'answer_book', unavailable)
    with pytest.raises(Exception, match='invalid citation'):
        await processor.generate(turn['id'])
    processor.fail(turn['id'], 'Citation validation failed')
    with database() as db:
        assert db.get(ChatThread, thread['id']).active_turn_id is None
        assert db.get(ChatTurn, turn['id']).sources
    retry = client.post(f"/api/chats/{thread['id']}/messages/{turn['id']}/retry")
    assert retry.status_code == 202 and retry.json()['status'] == 'pending'
    processor.fail(turn['id'], 'Late failure from attempt zero', attempt=0)
    with database() as db:
        assert db.get(ChatTurn, turn['id']).status == 'pending'
        assert db.get(ChatThread, thread['id']).active_turn_id == turn['id']
    with pytest.raises(Exception, match='newer attempt'):
        await processor.generate(turn['id'], attempt=0)
    assert client.post(f"/api/chats/{thread['id']}/messages/{turn['id']}/retry").status_code == 409


@pytest.mark.skipif(os.getenv('TEMPORAL_TESTS') != '1', reason='Opt-in local Temporal integration; mocked provider only')
async def test_real_chat_workflow_activity_and_replay(client, database, monkeypatch):
    _, thread = book_and_chat(client)
    turn = ask(client, thread).json()

    async def answer(question, sources, *args, **kwargs):
        source = sources[0]
        return BookAnswer(answer='Anna finds a notebook.', supported=True, citations=[AnswerCitation(source_id=source.id, quote=source.text[:40])]), {"input_tokens": 1, "output_tokens": 1, "estimated_cost": 0}

    monkeypatch.setattr(ai, 'answer_book', answer)
    processor = ChatProcessor(database, client.app.runtime.config)
    temporal = await Client.connect('127.0.0.1:7323')
    queue = f'book-chat-test-{uuid4()}'
    async with Worker(temporal, task_queue=queue, workflows=[AnswerBookChat], activities=[processor.answer_activity, processor.fail_activity]):
        handle = await temporal.start_workflow(AnswerBookChat.run, {"turn_id": turn['id'], "attempt": 0}, id=queue, task_queue=queue, execution_timeout=timedelta(seconds=30))
        await asyncio.wait_for(handle.result(), 25)
        history = await handle.fetch_history()
    await Replayer(workflows=[AnswerBookChat]).replay_workflow(history)
    assert client.get(f"/api/chats/{thread['id']}").json()['turns'][0]['status'] == 'complete'
