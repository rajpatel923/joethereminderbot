import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.ai.client import AIClient, FALLBACK_MESSAGE
from openai import APIConnectionError, APIStatusError


@pytest.fixture
def ai_client(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("VLLM_MODEL_NAME", "test-model")
    with patch("src.ai.client.AsyncOpenAI"):
        client = AIClient()
    return client


@pytest.mark.asyncio
async def test_successful_chat(ai_client):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "  Hello there!  "
    ai_client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await ai_client.chat([{"role": "user", "content": "hi"}])
    assert result == "Hello there!"


@pytest.mark.asyncio
async def test_connection_error_returns_fallback(ai_client):
    ai_client._client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    result = await ai_client.chat([{"role": "user", "content": "hi"}])
    assert result == FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_unexpected_error_returns_fallback(ai_client):
    ai_client._client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    result = await ai_client.chat([{"role": "user", "content": "hi"}])
    assert result == FALLBACK_MESSAGE
