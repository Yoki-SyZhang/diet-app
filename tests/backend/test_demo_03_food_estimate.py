"""1.7 LLM 直接估算 + 确认预览:kcal 非空才算 resolved、null 传播、source_tag/置信度
标注正确、并发批次里的部分失败不丢项也不阻塞其他项(tasks/current.md)。全部用 stub
`LlmClient`,不打真实网络。
"""

import pytest

from app.schemas.diet_parse import ParsedFoodItem
from app.schemas.llm_outcome import LlmOutcome
from app.services.food_estimate import estimate_food, estimate_items
from app.services.llm_client import LlmJsonResult


class RoutingStubLlmClient:
    """按 user prompt 里是否包含某个食物名路由到对应预置响应,不依赖调用顺序——
    estimate_items 内部是并发调用,不能假设 stub 按固定顺序被消费。"""

    def __init__(self, responses_by_food_name: dict[str, LlmJsonResult]) -> None:
        self._responses = responses_by_food_name
        self.calls: list[str] = []

    async def chat_json(self, *, system: str, user: str, temperature: float = 0.0):
        self.calls.append(user)
        for food_name, result in self._responses.items():
            if food_name in user:
                return result
        raise AssertionError(f"no stub response configured for prompt: {user}")


def _resolved_payload(**overrides):
    payload = {
        "kcal_100g": 165,
        "carb_100g": 0,
        "protein_100g": 31,
        "fat_100g": 3.6,
        "fiber_100g": 0,
        "confidence": "high",
        "confidence_reason": "常见食材,营养成分公开数据稳定",
    }
    payload.update(overrides)
    return payload


def _item(food_name="熟鸡胸肉", quantity=150, preparation_state="cooked") -> ParsedFoodItem:
    return ParsedFoodItem(
        food_name=food_name, quantity=quantity, unit="g", preparation_state=preparation_state
    )


@pytest.mark.asyncio
async def test_estimate_food_resolved_with_all_nutrients():
    client = RoutingStubLlmClient(
        {"熟鸡胸肉": LlmJsonResult(ok=True, parsed=_resolved_payload())}
    )
    result = await estimate_food(client, "熟鸡胸肉", "cooked")

    assert result.outcome == LlmOutcome.RESOLVED
    assert result.nutrients.kcal_100g == 165
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_estimate_food_partial_null_nutrients_propagate():
    payload = _resolved_payload(carb_100g=None, fiber_100g=None)
    client = RoutingStubLlmClient({"复合调味酱": LlmJsonResult(ok=True, parsed=payload)})
    result = await estimate_food(client, "复合调味酱", "cooked")

    assert result.outcome == LlmOutcome.RESOLVED
    assert result.nutrients.kcal_100g == 165
    assert result.nutrients.carb_100g is None
    assert result.nutrients.fiber_100g is None


@pytest.mark.asyncio
async def test_estimate_food_kcal_null_retries_then_invalid_model_output():
    payload = _resolved_payload(kcal_100g=None)
    client = RoutingStubLlmClient(
        {"未知食材": LlmJsonResult(ok=True, parsed=payload)}
    )
    result = await estimate_food(client, "未知食材", "cooked")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT
    assert len(client.calls) == 2  # 首次 + 一次重试


@pytest.mark.asyncio
async def test_estimate_food_ready_to_consume_resolves_and_prompt_uses_correct_label():
    client = RoutingStubLlmClient(
        {"牛奶": LlmJsonResult(ok=True, parsed=_resolved_payload(kcal_100g=54))}
    )
    result = await estimate_food(client, "牛奶", "ready_to_consume")

    assert result.outcome == LlmOutcome.RESOLVED
    assert result.nutrients.kcal_100g == 54
    assert "ready_to_consume" in client.calls[0]
    assert "即食" in client.calls[0] or "成品" in client.calls[0]


@pytest.mark.asyncio
async def test_estimate_food_service_unavailable_does_not_retry():
    client = RoutingStubLlmClient(
        {"熟鸡胸肉": LlmJsonResult(ok=False, error_kind="network", error_detail="超时")}
    )
    result = await estimate_food(client, "熟鸡胸肉", "cooked")

    assert result.outcome == LlmOutcome.SERVICE_UNAVAILABLE
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_estimate_food_invalid_confidence_value_is_contract_violation():
    payload = _resolved_payload(confidence="super-high")
    client = RoutingStubLlmClient({"熟鸡胸肉": LlmJsonResult(ok=True, parsed=payload)})
    result = await estimate_food(client, "熟鸡胸肉", "cooked")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_estimate_items_partial_failure_preserves_order_and_does_not_drop():
    client = RoutingStubLlmClient(
        {
            "熟鸡胸肉": LlmJsonResult(ok=True, parsed=_resolved_payload(kcal_100g=165)),
            "生西兰花": LlmJsonResult(
                ok=False, error_kind="network", error_detail="连接失败"
            ),
        }
    )
    items = [
        _item(food_name="熟鸡胸肉", quantity=150, preparation_state="cooked"),
        _item(food_name="生西兰花", quantity=100, preparation_state="raw"),
    ]

    results = await estimate_items(client, items, meal_slot="lunch")

    assert len(results) == 2
    assert results[0].parsed_item.food_name == "熟鸡胸肉"
    assert results[0].outcome == LlmOutcome.RESOLVED
    assert results[0].preview is not None
    assert results[1].parsed_item.food_name == "生西兰花"
    assert results[1].outcome == LlmOutcome.SERVICE_UNAVAILABLE
    assert results[1].preview is None
    assert results[1].message is not None


@pytest.mark.asyncio
async def test_estimate_items_preview_has_correct_snapshot_and_source_tag():
    client = RoutingStubLlmClient(
        {"熟鸡胸肉": LlmJsonResult(ok=True, parsed=_resolved_payload(kcal_100g=200))}
    )
    items = [_item(food_name="熟鸡胸肉", quantity=150, preparation_state="cooked")]

    results = await estimate_items(client, items, meal_slot="dinner")
    preview = results[0].preview

    assert preview.source_tag == "llm_estimate"
    assert preview.meal_slot == "dinner"
    assert preview.warning == "可能不准"
    assert preview.nutrients.kcal == 300  # 200 * 150 / 100
    assert "date" not in type(preview).model_fields
    assert "created_at" not in type(preview).model_fields


@pytest.mark.asyncio
async def test_estimate_items_handles_ready_to_consume_item():
    client = RoutingStubLlmClient(
        {"牛奶": LlmJsonResult(ok=True, parsed=_resolved_payload(kcal_100g=54, protein_100g=3.2))}
    )
    items = [_item(food_name="牛奶", quantity=250, preparation_state="ready_to_consume")]

    results = await estimate_items(client, items, meal_slot="breakfast")

    assert results[0].outcome == LlmOutcome.RESOLVED
    assert results[0].preview.nutrients.kcal == 135  # 54 * 250 / 100
