"""1.8 基础设施:DashScopeClient 的失败通道要落到结构化 LlmJsonResult,不抛异常
(tasks/current.md)。全部用 httpx.MockTransport,不打真实网络。
"""

import json

import httpx
import pytest

from app.config import settings
from app.services.llm_client import DashScopeClient, create_dashscope_client


def _client_with_handler(
    handler,
    *,
    api_key: str | None = "test-key",
    max_retries: int = 2,
    max_concurrency: int = 4,
) -> DashScopeClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return DashScopeClient(
        http_client,
        api_key=api_key,
        base_url="https://example.invalid/v1",
        model="qwen-plus",
        max_concurrency=max_concurrency,
        max_retries=max_retries,
    )


def _openai_style_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.asyncio
async def test_valid_json_response_returns_ok_with_parsed_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_style_response('{"meal_slot": "lunch"}'))

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is True
    assert result.parsed == {"meal_slot": "lunch"}
    assert result.error_kind is None


@pytest.mark.asyncio
async def test_200_with_invalid_json_content_is_response_not_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_style_response("not valid json{{"))

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "response_not_json"


@pytest.mark.asyncio
async def test_200_with_unexpected_body_shape_is_response_not_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "response_not_json"


@pytest.mark.asyncio
async def test_non_retryable_http_error_fails_without_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, text="bad request")

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "http_error"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_429_retries_then_succeeds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_openai_style_response('{"ok": true}'))

    client = _client_with_handler(handler, max_retries=2)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is True
    assert result.parsed == {"ok": True}
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_429_exhausts_retries_and_fails():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, text="rate limited")

    client = _client_with_handler(handler, max_retries=2)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "http_error"
    assert len(calls) == 3  # 首次 + 2 次重试


@pytest.mark.asyncio
async def test_network_exception_maps_to_network_error_kind():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "network"


@pytest.mark.asyncio
async def test_timeout_exception_maps_to_network_error_kind():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client_with_handler(handler)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "network"


@pytest.mark.asyncio
async def test_missing_api_key_is_not_configured_without_sending_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_openai_style_response("{}"))

    client = _client_with_handler(handler, api_key=None)
    result = await client.chat_json(system="s", user="u")

    assert result.ok is False
    assert result.error_kind == "not_configured"
    assert len(calls) == 0


def test_create_dashscope_client_reads_config_from_settings():
    # 用 MockTransport 占位,只为了不在构造 AsyncClient 时触发真实 SSL/网络初始化
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    client = create_dashscope_client(http_client)

    assert client._api_key == settings.dashscope_api_key
    assert client._base_url == settings.dashscope_base_url.rstrip("/")
    assert client._model == settings.llm_text_model
