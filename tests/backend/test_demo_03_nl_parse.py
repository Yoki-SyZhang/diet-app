"""1.8 自然语言解析:intent×outcome 两维结果在代码层的正确性——不测 LLM 语义判断质量
(裸词该不该追问生熟、菜名判断准不准),那部分由 `backend/scripts/eval_nl_parse.py` 的
真实评测集覆盖(tasks/current.md)。这里全部用 stub `LlmClient`,不打真实网络。
"""

import pytest

from app.schemas.diet_parse import Intent
from app.schemas.llm_outcome import LlmOutcome
from app.services.llm_client import LlmJsonResult
from app.services.nl_parse import _SYSTEM_PROMPT, parse_diet_text


class StubLlmClient:
    def __init__(self, results: list[LlmJsonResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, *, system: str, user: str, temperature: float = 0.0):
        self.calls.append((system, user))
        return self._results.pop(0)


def _resolved_payload(**overrides):
    payload = {
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
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_resolved_full_info():
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=_resolved_payload())])
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.intent == Intent.NEW_ENTRY
    assert result.outcome == LlmOutcome.RESOLVED
    assert result.meal_slot == "lunch"
    assert result.message is None
    assert len(result.items) == 1
    item = result.items[0]
    assert item.food_name == "熟鸡胸肉"
    assert item.quantity == 150
    assert item.unit == "g"
    assert item.preparation_state == "cooked"


@pytest.mark.asyncio
async def test_resolved_multi_item_dish_names_carry_through_unchanged():
    payload = _resolved_payload(
        items=[
            {"food_name": "烤玉米", "quantity": 200, "unit": "g", "preparation_state": "cooked"},
            {
                "food_name": "蒜蓉西兰花",
                "quantity": 100,
                "unit": "g",
                "preparation_state": "cooked",
            },
        ]
    )
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "吃了烤玉米和蒜蓉西兰花")

    assert result.outcome == LlmOutcome.RESOLVED
    assert [item.food_name for item in result.items] == ["烤玉米", "蒜蓉西兰花"]


@pytest.mark.asyncio
async def test_resolved_ready_to_consume_items_do_not_need_prep_state_question():
    # 牛奶/酸奶/面包等即食即饮成品:生熟区分没有意义,直接 ready_to_consume,不追问
    payload = _resolved_payload(
        meal_slot="breakfast",
        items=[
            {
                "food_name": "牛奶",
                "quantity": 250,
                "unit": "g",
                "preparation_state": "ready_to_consume",
            },
            {
                "food_name": "全麦面包",
                "quantity": 60,
                "unit": "g",
                "preparation_state": "ready_to_consume",
            },
        ],
    )
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "早餐喝了一杯牛奶、吃了一片全麦面包")

    assert result.outcome == LlmOutcome.RESOLVED
    assert [item.preparation_state for item in result.items] == [
        "ready_to_consume",
        "ready_to_consume",
    ]
    assert [item.food_name for item in result.items] == ["牛奶", "全麦面包"]


@pytest.mark.asyncio
async def test_needs_clarification_missing_quantity():
    payload = {
        "intent": "new_entry",
        "status": "needs_clarification",
        "message": "大概吃了多少克鸡胸肉呢?",
    }
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "我吃了鸡胸肉")

    assert result.intent == Intent.NEW_ENTRY
    assert result.outcome == LlmOutcome.NEEDS_CLARIFICATION
    assert result.items == []
    assert result.message == "大概吃了多少克鸡胸肉呢?"


@pytest.mark.asyncio
async def test_needs_clarification_bare_ingredient_missing_prep_state():
    payload = {
        "intent": "new_entry",
        "status": "needs_clarification",
        "message": "鸡胸肉是生的还是熟的呢?",
    }
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "我吃了150g鸡胸肉")

    assert result.outcome == LlmOutcome.NEEDS_CLARIFICATION
    assert result.items == []


@pytest.mark.asyncio
async def test_no_log_intent_chitchat_returns_message_without_outcome():
    # 闲聊/问常识:intent=no_log_intent,outcome 为 None,message 直接是回应文案
    payload = {"intent": "no_log_intent", "message": "我主要帮你记录饮食,今天吃了什么呀?"}
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "今天天气怎么样")

    assert result.intent == Intent.NO_LOG_INTENT
    assert result.outcome is None
    assert result.items == []
    assert result.message == "我主要帮你记录饮食,今天吃了什么呀?"


@pytest.mark.asyncio
async def test_edit_existing_entry_returns_message_without_outcome():
    # 想改已写库的记录:intent=edit_existing_entry,当前不支持,message 是得体的说明
    payload = {"intent": "edit_existing_entry", "message": "目前还不支持修改已经记录的内容"}
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "帮我把昨天记的鸡胸肉删掉")

    assert result.intent == Intent.EDIT_EXISTING_ENTRY
    assert result.outcome is None
    assert result.items == []
    assert result.message == "目前还不支持修改已经记录的内容"


@pytest.mark.asyncio
async def test_correct_pending_item_resolved_carries_items():
    # 修改重新估算路径:模型自我确认 intent=correct_pending_item,outcome 语义同 new_entry
    payload = _resolved_payload(intent="correct_pending_item")
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "原来识别:熟鸡胸肉100g;用户修正:改成150g")

    assert result.intent == Intent.CORRECT_PENDING_ITEM
    assert result.outcome == LlmOutcome.RESOLVED
    assert len(result.items) == 1


@pytest.mark.asyncio
async def test_missing_intent_is_contract_violation():
    # 旧版单维 payload(没有 intent 字段)现在属于契约违规,重试后仍缺 → invalid_model_output
    payload = _resolved_payload()
    payload.pop("intent")
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed=dict(payload)), LlmJsonResult(ok=True, parsed=dict(payload))]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_unknown_intent_value_is_contract_violation():
    payload = _resolved_payload(intent="delete_everything")
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed=payload), LlmJsonResult(ok=True, parsed=payload)]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT


@pytest.mark.asyncio
async def test_no_log_intent_missing_message_is_contract_violation():
    # no_log_intent/edit_existing_entry 的 message 必须非空,缺了就是契约违规
    payload = {"intent": "no_log_intent"}
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed=dict(payload)), LlmJsonResult(ok=True, parsed=dict(payload))]
    )
    result = await parse_diet_text(client, "早上好")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT


@pytest.mark.asyncio
async def test_service_unavailable_does_not_retry():
    client = StubLlmClient([LlmJsonResult(ok=False, error_kind="network", error_detail="连接超时")])
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.SERVICE_UNAVAILABLE
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_not_configured_maps_to_service_unavailable():
    client = StubLlmClient(
        [LlmJsonResult(ok=False, error_kind="not_configured", error_detail="缺 Key")]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_response_not_json_retries_once_then_succeeds():
    client = StubLlmClient(
        [
            LlmJsonResult(ok=False, error_kind="response_not_json", error_detail="坏 JSON"),
            LlmJsonResult(ok=True, parsed=_resolved_payload()),
        ]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.RESOLVED
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_response_not_json_exhausts_retry_and_fails():
    client = StubLlmClient(
        [
            LlmJsonResult(ok=False, error_kind="response_not_json", error_detail="坏 JSON 1"),
            LlmJsonResult(ok=False, error_kind="response_not_json", error_detail="坏 JSON 2"),
        ]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_schema_violation_retries_once_then_succeeds():
    bad_payload = _resolved_payload(
        items=[{"food_name": "", "quantity": 150, "unit": "g", "preparation_state": "cooked"}]
    )
    client = StubLlmClient(
        [
            LlmJsonResult(ok=True, parsed=bad_payload),
            LlmJsonResult(ok=True, parsed=_resolved_payload()),
        ]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.RESOLVED
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_schema_violation_exhausts_retry_and_fails():
    bad_payload = _resolved_payload(
        items=[{"food_name": "x", "quantity": -1, "unit": "g", "preparation_state": "cooked"}]
    )
    client = StubLlmClient(
        [
            LlmJsonResult(ok=True, parsed=bad_payload),
            LlmJsonResult(ok=True, parsed=bad_payload),
        ]
    )
    result = await parse_diet_text(client, "我吃了150g熟鸡胸肉")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_preparation_state_unknown_is_rejected_as_contract_violation():
    # unknown 保留给"确实无法判断"的语义,不是这个字段会用到的合法值——模型如果输出它,
    # 属于契约违规,不是"这个食物不适用生熟区分"(那种情况应该是 ready_to_consume)。
    bad_payload = _resolved_payload(
        items=[
            {"food_name": "神秘食物", "quantity": 100, "unit": "g", "preparation_state": "unknown"}
        ]
    )
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed=bad_payload), LlmJsonResult(ok=True, parsed=bad_payload)]
    )
    result = await parse_diet_text(client, "我吃了100g神秘食物")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT


@pytest.mark.asyncio
async def test_unknown_status_value_is_contract_violation():
    payload = {"intent": "new_entry", "status": "who_knows", "message": "?"}
    client = StubLlmClient([LlmJsonResult(ok=True, parsed=payload), LlmJsonResult(ok=True, parsed=payload)])
    result = await parse_diet_text(client, "随便")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT


@pytest.mark.asyncio
async def test_serving_unit_is_rejected_as_contract_violation():
    # Demo 阶段只允许 g(§7.1),模型如果输出 serving 属于契约违规
    bad_payload = _resolved_payload(
        items=[
            {
                "food_name": "我的燕麦碗",
                "quantity": 1,
                "unit": "serving",
                "preparation_state": "cooked",
            }
        ]
    )
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed=bad_payload), LlmJsonResult(ok=True, parsed=bad_payload)]
    )
    result = await parse_diet_text(client, "我吃了一碗我的燕麦碗")

    assert result.outcome == LlmOutcome.INVALID_MODEL_OUTPUT


def test_prompt_contains_lowercase_json_for_dashscope_json_object_mode():
    assert "json" in _SYSTEM_PROMPT
