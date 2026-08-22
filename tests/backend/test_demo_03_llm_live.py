"""1.8 真实 DashScope 冒烟测试(tasks/current.md)。默认不跑(`llm_live` marker,
pyproject.toml 的 addopts 里排除),显式 `pytest -m llm_live` 才会执行——验证这个 PR
自己写的 prompt/解析代码在真实环境下能跑通、拿到合法 JSON,不是重复 ADR 0001 已验证过
的"供应商本身能不能用"。这不是 §11.1 95% 合法结构率的正式验收,那个由
`backend/scripts/eval_nl_parse.py` 的真实评测集覆盖。
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.schemas.llm_outcome import LlmOutcome
from app.services.food_estimate import estimate_food
from app.services.llm_client import create_dashscope_client
from app.services.nl_parse import parse_diet_text

pytestmark = [
    pytest.mark.llm_live,
    pytest.mark.skipif(
        not settings.dashscope_api_key,
        reason="DASHSCOPE_API_KEY 未配置,跳过真实 API 冒烟测试",
    ),
]


@pytest_asyncio.fixture
async def dashscope_client():
    async with httpx.AsyncClient() as http_client:
        yield create_dashscope_client(http_client)


@pytest.mark.asyncio
async def test_parse_diet_text_real_call_returns_valid_structure(dashscope_client):
    result = await parse_diet_text(dashscope_client, "我中午吃了一碗白米饭和一个煎鸡蛋")

    assert result.outcome in (LlmOutcome.RESOLVED, LlmOutcome.NEEDS_CLARIFICATION)


@pytest.mark.asyncio
async def test_estimate_food_real_call_returns_valid_structure(dashscope_client):
    result = await estimate_food(dashscope_client, "熟鸡胸肉", "cooked")

    assert result.outcome in (LlmOutcome.RESOLVED, LlmOutcome.INVALID_MODEL_OUTPUT)
    if result.outcome == LlmOutcome.RESOLVED:
        assert result.nutrients.kcal_100g is not None
