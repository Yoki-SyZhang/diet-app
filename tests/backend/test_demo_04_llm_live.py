"""1.9 真实 DashScope API 冒烟测试(和 `test_demo_03_llm_live.py` 同一套约定:
`llm_live` marker 默认不跑,`pytest -m llm_live` 显式触发,Key 未配置则跳过)。

1.9 新增了三处会实际改变 prompt/契约形状的 LLM 调用点,这里对每一处各跑一次真实调用,
只断言"结构/契约合法性",不断言具体文案(语义准确率是 eval_nl_parse.py 数据集的职责):

1. `parse_diet_text` 带非空 today_context——intent/outcome 两维契约上线后第一次跟真实
   模型对齐,最容易在这里发现"模型返回的字段名/取值和 Pydantic schema 对不上"。
2. `handle_modify_correction` 用真实合成文本——返回合法 `ItemEstimateOutcome` 或有意义
   的 failure_reason,不抛异常。
3. `recap_batch_status`——`{"summary": ...}` 契约真实返回,或正确触发确定性兜底文案。
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.schemas.chat import BatchItemStatus
from app.schemas.diet_parse import Intent, ParsedFoodItem
from app.schemas.llm_outcome import LlmOutcome
from app.services.chat_turn import handle_modify_correction, recap_batch_status
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


_TODAY_CONTEXT = (
    "今日对话记录:\n"
    "[用户] 早上吃了一个煮鸡蛋\n"
    "[AI] 我识别到了(早餐):煮鸡蛋 50g。请在下方卡片里确认或修改。\n"
    "[AI] 已记录煮鸡蛋50g。\n\n"
    "今日已确认记录的饮食明细:\n"
    "| 餐次 | 食物 | 数量 | kcal | 碳水(g) | 蛋白质(g) | 脂肪(g) | 纤维(g) |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| 早餐 | 煮鸡蛋 | 50g | 72 | 0.6 | 6.3 | 4.8 | — |"
)


def _assert_intent_outcome_contract(result) -> None:
    assert result.intent in list(Intent)
    if result.intent in (Intent.NEW_ENTRY, Intent.CORRECT_PENDING_ITEM):
        assert result.outcome in list(LlmOutcome)
    else:
        assert result.outcome is None
        assert result.message
        assert result.items == []


@pytest.mark.asyncio
async def test_parse_with_today_context_returns_valid_two_dim_structure(dashscope_client):
    result = await parse_diet_text(
        dashscope_client,
        "中午吃了150g熟鸡胸肉和一碗白米饭",
        today_context=_TODAY_CONTEXT,
    )
    _assert_intent_outcome_contract(result)


@pytest.mark.asyncio
async def test_parse_no_log_intent_with_context(dashscope_client):
    result = await parse_diet_text(
        dashscope_client, "你觉得我今天吃得健康吗?", today_context=_TODAY_CONTEXT
    )
    _assert_intent_outcome_contract(result)


@pytest.mark.asyncio
async def test_modify_correction_real_call(dashscope_client, db_session):
    original = ParsedFoodItem(
        food_name="熟鸡胸肉", quantity=100, unit="g", preparation_state="cooked"
    )
    result = await handle_modify_correction(
        db_session, dashscope_client, original, "lunch", "改成200g", "conf-live-1"
    )

    assert result.confirmation_id == "conf-live-1"
    if result.success:
        assert result.outcome is not None
        assert result.outcome.outcome == LlmOutcome.RESOLVED
        assert result.outcome.preview is not None
        assert result.outcome.preview.nutrients.kcal is not None
        assert result.outcome.preview.meal_slot == "lunch"
    else:
        assert result.failure_reason  # 失败也必须给出有意义的原因,不留白


@pytest.mark.asyncio
async def test_recap_real_call_produces_nonblank_message(dashscope_client, db_session):
    items = [
        BatchItemStatus(food_name="熟鸡胸肉", quantity=200, state="confirmed", kcal=330.0),
        BatchItemStatus(food_name="白米饭", quantity=150, state="confirmed", kcal=174.0),
        BatchItemStatus(food_name="可乐", quantity=330, state="abandoned"),
    ]
    message = await recap_batch_status(
        db_session, dashscope_client, "batch-live-1", "lunch", items
    )

    # LLM 正常返回或确定性兜底都可以,但绝不能留白
    assert message.content.strip()
    assert message.kind == "recap"
    assert message.batch_id == "batch-live-1"
