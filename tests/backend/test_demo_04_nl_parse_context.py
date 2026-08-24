"""1.9 `parse_diet_text` 的 `today_context` 参数:传入时进 prompt(用户消息里,分段
清晰)、不传时行为与 1.8 完全一致(向后兼容,原有调用方零改动)。
"""

import pytest

from app.schemas.llm_outcome import LlmOutcome
from app.services.llm_client import LlmJsonResult
from app.services.nl_parse import parse_diet_text


class StubLlmClient:
    def __init__(self, results: list[LlmJsonResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, *, system: str, user: str, temperature: float = 0.0):
        self.calls.append((system, user))
        return self._results.pop(0)


def _resolved():
    return LlmJsonResult(
        ok=True,
        parsed={
            "intent": "new_entry",
            "status": "resolved",
            "meal_slot": "lunch",
            "items": [
                {
                    "food_name": "熟鸡胸肉",
                    "quantity": 150,
                    "unit": "g",
                    "preparation_state": "cooked",
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_without_context_user_message_is_raw_text():
    client = StubLlmClient([_resolved()])
    await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    _, user = client.calls[0]
    assert user == "我吃了150g熟鸡胸肉"


@pytest.mark.asyncio
async def test_with_context_user_message_contains_both_sections():
    client = StubLlmClient([_resolved()])
    context = "今日对话记录:\n[用户] 早上吃了鸡蛋\n\n今日已确认记录的饮食明细:\n| 餐次 |"
    await parse_diet_text(client, "我吃了150g熟鸡胸肉", today_context=context)

    _, user = client.calls[0]
    assert "【今日情况" in user
    assert "[用户] 早上吃了鸡蛋" in user
    assert "【用户本次消息" in user
    assert user.index("早上吃了鸡蛋") < user.index("我吃了150g熟鸡胸肉")
    assert user.rstrip().endswith("我吃了150g熟鸡胸肉")


@pytest.mark.asyncio
async def test_empty_context_treated_as_absent():
    client = StubLlmClient([_resolved()])
    await parse_diet_text(client, "我吃了150g熟鸡胸肉", today_context="")

    _, user = client.calls[0]
    assert user == "我吃了150g熟鸡胸肉"


@pytest.mark.asyncio
async def test_context_kept_across_internal_retry():
    # 契约违规自动重试的第二次调用,today_context 也必须还在
    bad = LlmJsonResult(ok=False, error_kind="response_not_json", error_detail="坏 JSON")
    client = StubLlmClient([bad, _resolved()])
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉", today_context="今日对话记录:x")

    assert result.outcome == LlmOutcome.RESOLVED
    assert len(client.calls) == 2
    assert client.calls[0][1] == client.calls[1][1]
    assert "今日对话记录:x" in client.calls[1][1]
