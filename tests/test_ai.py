import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai.exceptions import UnexpectedModelBehavior

from backend.app.ai import client as ai
from backend.app.ai.schemas import ExtractedPages, GeneratedLearning
from backend.app.core.config import chat_reasoning_effort
from backend.app.sample import LEARNING, LEFT, RIGHT


@pytest.mark.parametrize(
    "model,effort",
    [
        ("Qwen/Qwen3.5-397B-A17B", "none"),
        ("deepseek-ai/DeepSeek-V4.1-Flash-1017", 1),
        ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "1"),
        ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "low"),
    ],
)
async def test_pydanticai_deepinfra_request_and_output_validation(database, monkeypatch, model, effort):
    monkeypatch.setattr(ai.settings(), "deepinfra_model", model)
    monkeypatch.setattr(ai.settings(), "deepinfra_reasoning_effort", effort)
    requests = []

    def provider(request):
        requests.append(json.loads(request.content))
        assert str(request.url).endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"left": LEFT, "right": RIGHT, "readable": True, "warnings": []}
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            },
        )

    def fake_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))

    monkeypatch.setattr(ai, "AsyncOpenAI", fake_client)
    output, metrics = await ai.request(ExtractedPages, "Read both pages")
    assert output.left == LEFT and output.right == RIGHT
    assert metrics["input_tokens"] == 100 and metrics["output_tokens"] == 200
    assert len(requests) == 1
    assert requests[0]["model"] == model
    assert requests[0]["reasoning_effort"] == ("low" if effort in (1, "1") else effort)
    assert isinstance(requests[0]["reasoning_effort"], str)
    assert requests[0]["max_tokens"] == 16000
    assert "max_completion_tokens" not in requests[0]
    assert requests[0]["temperature"] == ai.settings().deepinfra_temperature
    assert requests[0]["top_p"] == ai.settings().deepinfra_top_p


@pytest.mark.parametrize("value", [0, 50, 100, True, "invalid"])
def test_unsupported_reasoning_effort_fails_locally(value):
    with pytest.raises(ValueError, match="named reasoning effort"):
        chat_reasoning_effort(value)


async def test_failed_quote_validation_identifies_the_expression(database, monkeypatch):
    payload = {**LEARNING, "expressions": [{**entry} for entry in LEARNING["expressions"] * 2]}
    payload["expressions"][0]["source_sentence"] = "Invented quotation."

    def provider(_request):
        return httpx.Response(
            200,
            json={
                "id": "test-validation",
                "object": "chat.completion",
                "created": 1,
                "model": "Qwen/Qwen3.5-397B-A17B",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    def fake_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))

    monkeypatch.setattr(ai, "AsyncOpenAI", fake_client)
    with pytest.raises(UnexpectedModelBehavior, match="catch sight of"):
        await ai.request(
            GeneratedLearning, "Create learning material", extraction=ExtractedPages(left=LEFT, right=RIGHT, readable=True)
        )
