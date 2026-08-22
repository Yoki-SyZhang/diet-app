"""供应商无关的 LLM 适配层(1.8 基础设施,ADR 0001)。`DashScopeClient` 是第一个也是
当前唯一实现;`nl_parse`/`food_estimate` 依赖 `LlmClient` 这个 Protocol,不直接依赖
`DashScopeClient`,方便测试注入 stub、也方便未来切换/新增供应商。

失败统一走结构化的 `LlmJsonResult(ok=False, ...)` 返回值,不抛异常给调用方——
调用方(nl_parse/food_estimate)据此把 error_kind 映射到 LlmOutcome:
network/http_error/not_configured → service_unavailable;
response_not_json → invalid_model_output 的一种输入(还要再叠加"JSON 合法但不满足我们
自己 Pydantic 契约"这一层,那一层校验在调用方做,这里管不到)。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.config import settings

ErrorKind = Literal["network", "http_error", "response_not_json", "not_configured"]

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LlmJsonResult:
    ok: bool
    parsed: dict | list | None = None
    error_kind: ErrorKind | None = None
    error_detail: str | None = None


class LlmClient(Protocol):
    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.0
    ) -> LlmJsonResult: ...


class DashScopeClient:
    """阿里云百炼(DashScope)OpenAI 兼容 endpoint,纯文本路由固定 `qwen-plus`(ADR 0001)。

    `response_format: json_object` 只是尽量约束模型输出,响应仍然原样返回给调用方
    去过 Pydantic 校验——不假设这个约束模式能替代校验(ADR 0001 的结论)。
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        max_concurrency: int,
        max_retries: int,
    ) -> None:
        # 全部参数必须显式传入,不在构造函数里"没传就退回 settings"——那种隐式回退会让
        # api_key=None(测试里故意模拟未配置 Key)和"没传这个参数"两种意图混在一起,
        # 导致本该测到 not_configured 的用例悄悄用了 settings 里配置的真实 Key。
        # 生产代码请用下面的 create_dashscope_client(),不要直接传 None/留空调这个类。
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.0
    ) -> LlmJsonResult:
        if not self._api_key:
            return LlmJsonResult(
                ok=False,
                error_kind="not_configured",
                error_detail="DASHSCOPE_API_KEY 未配置,AI 服务不可用",
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        timeout = httpx.Timeout(
            settings.llm_total_timeout_seconds, connect=settings.llm_connect_timeout_seconds
        )

        async with self._semaphore:
            response: httpx.Response | None = None
            for attempt in range(self._max_retries + 1):
                try:
                    response = await self._client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=timeout,
                    )
                except httpx.TimeoutException as exc:
                    return LlmJsonResult(
                        ok=False, error_kind="network", error_detail=f"请求超时: {exc}"
                    )
                except httpx.HTTPError as exc:
                    return LlmJsonResult(
                        ok=False, error_kind="network", error_detail=f"网络错误: {exc}"
                    )

                if response.status_code == 200:
                    break
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return LlmJsonResult(
                    ok=False,
                    error_kind="http_error",
                    error_detail=f"HTTP {response.status_code}: {response.text[:200]}",
                )

        assert response is not None
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return LlmJsonResult(
                ok=False,
                error_kind="response_not_json",
                error_detail=f"响应不是合法 JSON: {exc}",
            )

        return LlmJsonResult(ok=True, parsed=parsed)


def create_dashscope_client(client: httpx.AsyncClient) -> DashScopeClient:
    """按 `app.config.settings` 构造生产用的 `DashScopeClient`。1.9 的路由层、评测脚本
    都应该调这个工厂,不要直接实例化 `DashScopeClient`——配置项变了只用改
    `Settings`,不用满仓库找构造调用点。"""
    return DashScopeClient(
        client,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.llm_text_model,
        max_concurrency=settings.llm_max_concurrency,
        max_retries=settings.llm_max_retries,
    )
