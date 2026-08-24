"""1.9 编排层:`handle_new_message`(intent×outcome 分支、today_context 组装、部分/全部
估算失败)、`handle_modify_correction`(不带 today_context、不写 chat_message)、
`find_open_batch`(四种判定)、`recap_batch_status`(LLM 成功/失败兜底)。全部用 stub
`LlmClient`,不打真实网络;真实模型的契约对齐由 `test_demo_04_llm_live.py` 负责。
"""

import json
from datetime import datetime, timezone

import pytest

from app.models.chat_message import ChatMessage
from app.schemas.chat import BatchItemStatus, ConfirmableItem
from app.schemas.diet_parse import Intent, ParsedFoodItem
from app.schemas.food_estimate import ConfirmationPreview, ItemEstimateOutcome
from app.schemas.llm_outcome import LlmOutcome
from app.schemas.nutrition import NutrientSet
from app.services.chat import record_chat_message
from app.services.chat_turn import (
    find_open_batch,
    handle_modify_correction,
    handle_new_message,
    recap_batch_status,
)
from app.services.llm_client import LlmJsonResult
from app.services.meal_entry_write import confirm_meal_entry

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)  # 上海本地 20:00,归 2026-08-24


class StubLlmClient:
    def __init__(self, results: list[LlmJsonResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, *, system: str, user: str, temperature: float = 0.0):
        self.calls.append((system, user))
        return self._results.pop(0)


def _parse_resolved(items=None, meal_slot="lunch", intent="new_entry") -> LlmJsonResult:
    if items is None:
        items = [
            {"food_name": "熟鸡胸肉", "quantity": 150, "unit": "g", "preparation_state": "cooked"}
        ]
    return LlmJsonResult(
        ok=True,
        parsed={"intent": intent, "status": "resolved", "meal_slot": meal_slot, "items": items},
    )


def _estimate_ok(kcal=165) -> LlmJsonResult:
    return LlmJsonResult(
        ok=True,
        parsed={
            "kcal_100g": kcal,
            "carb_100g": 0,
            "protein_100g": 31,
            "fat_100g": 3.6,
            "fiber_100g": None,
            "confidence": "high",
            "confidence_reason": "常见食材,营养数据稳定",
        },
    )


def _network_failure() -> LlmJsonResult:
    return LlmJsonResult(ok=False, error_kind="network", error_detail="连接超时")


def _chat_rows(db) -> list[ChatMessage]:
    return db.query(ChatMessage).order_by(ChatMessage.id).all()


def _confirmable(confirmation_id="conf-1", food_name="熟鸡胸肉", kcal=247.5) -> ConfirmableItem:
    item = ParsedFoodItem(
        food_name=food_name, quantity=150, unit="g", preparation_state="cooked"
    )
    preview = ConfirmationPreview(
        food_name=food_name,
        quantity=150,
        unit="g",
        meal_slot="lunch",
        nutrients=NutrientSet(kcal=kcal),
        source_tag="llm_estimate",
        confidence="high",
        confidence_reason="常见食材,营养数据稳定",
    )
    return ConfirmableItem(
        confirmation_id=confirmation_id,
        outcome=ItemEstimateOutcome(
            parsed_item=item, outcome=LlmOutcome.RESOLVED, preview=preview
        ),
    )


# ---------------------------------------------------------------------------
# handle_new_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_log_intent_replies_without_card(db_session):
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed={"intent": "no_log_intent", "message": "我主要帮你记录饮食"})]
    )
    result = await handle_new_message(db_session, client, "今天天气怎么样", now_utc=NOW)

    assert result.intent == Intent.NO_LOG_INTENT
    assert result.outcome is None
    assert result.batch_id is None
    assert result.items == []
    rows = _chat_rows(db_session)
    assert [(m.role, m.content) for m in rows] == [
        ("user", "今天天气怎么样"),
        ("assistant", "我主要帮你记录饮食"),
    ]
    assert rows[1].kind is None and rows[1].batch_id is None


@pytest.mark.asyncio
async def test_edit_existing_entry_replies_not_supported(db_session):
    client = StubLlmClient(
        [
            LlmJsonResult(
                ok=True,
                parsed={"intent": "edit_existing_entry", "message": "目前还不支持修改已有记录"},
            )
        ]
    )
    result = await handle_new_message(db_session, client, "把昨天的鸡胸肉删掉", now_utc=NOW)

    assert result.intent == Intent.EDIT_EXISTING_ENTRY
    assert result.outcome is None
    assert result.batch_id is None
    assert _chat_rows(db_session)[1].content == "目前还不支持修改已有记录"


@pytest.mark.asyncio
async def test_needs_clarification_replies_question_without_card(db_session):
    client = StubLlmClient(
        [
            LlmJsonResult(
                ok=True,
                parsed={
                    "intent": "new_entry",
                    "status": "needs_clarification",
                    "message": "大概吃了多少克呢?",
                },
            )
        ]
    )
    result = await handle_new_message(db_session, client, "我吃了鸡胸肉", now_utc=NOW)

    assert result.intent == Intent.NEW_ENTRY
    assert result.outcome == LlmOutcome.NEEDS_CLARIFICATION
    assert result.batch_id is None
    assert _chat_rows(db_session)[1].content == "大概吃了多少克呢?"


@pytest.mark.asyncio
async def test_service_unavailable_replies_error_message(db_session):
    client = StubLlmClient([_network_failure()])
    result = await handle_new_message(db_session, client, "我吃了150g熟鸡胸肉", now_utc=NOW)

    assert result.outcome == LlmOutcome.SERVICE_UNAVAILABLE
    assert result.batch_id is None
    assert "不可用" in _chat_rows(db_session)[1].content


@pytest.mark.asyncio
async def test_resolved_all_success_produces_card_with_signed_ids(db_session):
    items = [
        {"food_name": "熟鸡胸肉", "quantity": 150, "unit": "g", "preparation_state": "cooked"},
        {"food_name": "白米饭", "quantity": 200, "unit": "g", "preparation_state": "cooked"},
    ]
    client = StubLlmClient([_parse_resolved(items), _estimate_ok(165), _estimate_ok(116)])
    result = await handle_new_message(db_session, client, "午饭吃了鸡胸肉和米饭", now_utc=NOW)

    assert result.intent == Intent.NEW_ENTRY
    assert result.outcome == LlmOutcome.RESOLVED
    assert result.batch_id is not None
    assert len(result.items) == 2
    ids = {i.confirmation_id for i in result.items}
    assert len(ids) == 2  # 每项独立签发
    assert all(i.outcome.outcome == LlmOutcome.RESOLVED for i in result.items)

    assistant = _chat_rows(db_session)[1]
    assert assistant.kind == "recognition"
    assert assistant.batch_id == result.batch_id
    assert "熟鸡胸肉 150g" in assistant.content
    assert "白米饭 200g" in assistant.content
    assert "午餐" in assistant.content
    # 完整快照落库,能逐项还原成 ConfirmableItem
    snapshot = [
        ConfirmableItem.model_validate(raw) for raw in json.loads(assistant.food_summary_json)
    ]
    assert {i.confirmation_id for i in snapshot} == ids


@pytest.mark.asyncio
async def test_today_context_includes_history_but_not_current_message(db_session):
    record_chat_message(db_session, role="user", content="早上吃了一个鸡蛋", now_utc=NOW)
    confirm_meal_entry(
        db_session,
        _confirmable(food_name="煮鸡蛋").outcome.preview,
        "conf-egg",
        now_utc=NOW,
    )
    client = StubLlmClient([_parse_resolved(), _estimate_ok()])

    await handle_new_message(db_session, client, "中午吃了150g熟鸡胸肉", now_utc=NOW)

    _, user_prompt = client.calls[0]
    assert "早上吃了一个鸡蛋" in user_prompt  # 今日对话在 context 里
    assert "煮鸡蛋" in user_prompt  # 今日明细在 context 里
    # 这一轮刚发的消息只出现一次(在【用户本次消息】段),不在 context 里重复
    assert user_prompt.count("中午吃了150g熟鸡胸肉") == 1


@pytest.mark.asyncio
async def test_partial_estimate_failure_reported_in_text_not_in_items(db_session):
    items = [
        {"food_name": "熟鸡胸肉", "quantity": 150, "unit": "g", "preparation_state": "cooked"},
        {"food_name": "神秘炖菜", "quantity": 200, "unit": "g", "preparation_state": "cooked"},
    ]
    client = StubLlmClient([_parse_resolved(items), _estimate_ok(), _network_failure()])
    result = await handle_new_message(db_session, client, "吃了鸡胸肉和神秘炖菜", now_utc=NOW)

    assert len(result.items) == 1
    assert result.items[0].outcome.parsed_item.food_name == "熟鸡胸肉"
    assistant = _chat_rows(db_session)[1]
    assert "神秘炖菜" in assistant.content  # 失败项在播报里说明
    assert "不会出现在卡片里" in assistant.content
    snapshot = json.loads(assistant.food_summary_json)
    assert len(snapshot) == 1  # 快照只含进卡片的项


@pytest.mark.asyncio
async def test_all_estimates_fail_no_card_no_batch(db_session):
    client = StubLlmClient([_parse_resolved(), _network_failure()])
    result = await handle_new_message(db_session, client, "我吃了150g熟鸡胸肉", now_utc=NOW)

    assert result.batch_id is None
    assert result.items == []
    assistant = _chat_rows(db_session)[1]
    assert assistant.kind is None and assistant.batch_id is None
    assert assistant.food_summary_json is None
    assert "熟鸡胸肉" in assistant.content


# ---------------------------------------------------------------------------
# handle_modify_correction
# ---------------------------------------------------------------------------

_ORIGINAL = ParsedFoodItem(
    food_name="熟鸡胸肉", quantity=100, unit="g", preparation_state="cooked"
)


@pytest.mark.asyncio
async def test_modify_success_keeps_confirmation_id_and_writes_no_chat(db_session):
    corrected = [
        {"food_name": "熟鸡胸肉", "quantity": 200, "unit": "g", "preparation_state": "cooked"}
    ]
    client = StubLlmClient(
        [_parse_resolved(corrected, intent="correct_pending_item"), _estimate_ok()]
    )
    result = await handle_modify_correction(
        db_session, client, _ORIGINAL, "lunch", "改成200g", "conf-1", now_utc=NOW
    )

    assert result.success is True
    assert result.confirmation_id == "conf-1"
    assert result.outcome.outcome == LlmOutcome.RESOLVED
    assert result.outcome.preview.quantity == 200
    assert result.outcome.preview.meal_slot == "lunch"  # meal_slot 固定用传入值
    assert _chat_rows(db_session) == []  # 全程不写 chat_message

    # 合成文本含原识别信息+修正说明;不带 today_context
    _, user_prompt = client.calls[0]
    assert "熟鸡胸肉" in user_prompt
    assert "熟重100g" in user_prompt
    assert "改成200g" in user_prompt
    assert "今日对话记录" not in user_prompt
    assert "今日已确认" not in user_prompt


@pytest.mark.asyncio
async def test_modify_parse_needs_clarification_fails(db_session):
    client = StubLlmClient(
        [
            LlmJsonResult(
                ok=True,
                parsed={
                    "intent": "correct_pending_item",
                    "status": "needs_clarification",
                    "message": "想改成多少克呢?",
                },
            )
        ]
    )
    result = await handle_modify_correction(
        db_session, client, _ORIGINAL, "lunch", "量不对", "conf-1", now_utc=NOW
    )

    assert result.success is False
    assert result.outcome is None
    assert result.failure_reason == "想改成多少克呢?"
    assert _chat_rows(db_session) == []


@pytest.mark.asyncio
async def test_modify_parse_multiple_items_fails(db_session):
    two_items = [
        {"food_name": "熟鸡胸肉", "quantity": 200, "unit": "g", "preparation_state": "cooked"},
        {"food_name": "白米饭", "quantity": 100, "unit": "g", "preparation_state": "cooked"},
    ]
    client = StubLlmClient([_parse_resolved(two_items, intent="correct_pending_item")])
    result = await handle_modify_correction(
        db_session, client, _ORIGINAL, "lunch", "加一份米饭", "conf-1", now_utc=NOW
    )

    assert result.success is False
    assert "2 项" in result.failure_reason


@pytest.mark.asyncio
async def test_modify_estimate_failure_fails(db_session):
    corrected = [
        {"food_name": "熟鸡胸肉", "quantity": 200, "unit": "g", "preparation_state": "cooked"}
    ]
    client = StubLlmClient(
        [_parse_resolved(corrected, intent="correct_pending_item"), _network_failure()]
    )
    result = await handle_modify_correction(
        db_session, client, _ORIGINAL, "lunch", "改成200g", "conf-1", now_utc=NOW
    )

    assert result.success is False
    assert result.failure_reason is not None
    assert _chat_rows(db_session) == []


# ---------------------------------------------------------------------------
# find_open_batch
# ---------------------------------------------------------------------------


def _record_recognition(db, items: list[ConfirmableItem], batch_id="batch-1") -> None:
    record_chat_message(
        db,
        role="assistant",
        content="识别播报",
        batch_id=batch_id,
        kind="recognition",
        food_summary_json=json.dumps(
            [i.model_dump(mode="json") for i in items], ensure_ascii=False
        ),
        now_utc=NOW,
    )


def test_no_recognition_message_returns_none(db_session):
    record_chat_message(db_session, role="user", content="随便聊聊", now_utc=NOW)
    assert find_open_batch(db_session, now_utc=NOW) is None


def test_recognition_with_recap_returns_none(db_session):
    _record_recognition(db_session, [_confirmable("conf-1")])
    record_chat_message(
        db_session, role="assistant", content="已记录", batch_id="batch-1", kind="recap",
        now_utc=NOW,
    )
    assert find_open_batch(db_session, now_utc=NOW) is None


def test_all_items_written_returns_none(db_session):
    item = _confirmable("conf-1")
    _record_recognition(db_session, [item])
    confirm_meal_entry(db_session, item.outcome.preview, "conf-1", now_utc=NOW)

    assert find_open_batch(db_session, now_utc=NOW) is None


def test_partially_written_returns_missing_items_only(db_session):
    written = _confirmable("conf-1", food_name="熟鸡胸肉")
    missing = _confirmable("conf-2", food_name="白米饭")
    _record_recognition(db_session, [written, missing])
    confirm_meal_entry(db_session, written.outcome.preview, "conf-1", now_utc=NOW)

    open_batch = find_open_batch(db_session, now_utc=NOW)

    assert open_batch is not None
    assert open_batch.batch_id == "batch-1"
    assert [i.confirmation_id for i in open_batch.items] == ["conf-2"]
    assert open_batch.items[0].outcome.preview.food_name == "白米饭"


def test_nothing_written_returns_all_items(db_session):
    _record_recognition(db_session, [_confirmable("conf-1"), _confirmable("conf-2")])

    open_batch = find_open_batch(db_session, now_utc=NOW)

    assert open_batch is not None
    assert len(open_batch.items) == 2


def test_only_latest_recognition_counts(db_session):
    # 前一批已收尾,新一批未收尾:只看最后一条 recognition
    old = _confirmable("conf-old")
    _record_recognition(db_session, [old], batch_id="batch-old")
    record_chat_message(
        db_session, role="assistant", content="已记录", batch_id="batch-old", kind="recap",
        now_utc=NOW,
    )
    _record_recognition(db_session, [_confirmable("conf-new")], batch_id="batch-new")

    open_batch = find_open_batch(db_session, now_utc=NOW)

    assert open_batch is not None
    assert open_batch.batch_id == "batch-new"


def test_corrupted_snapshot_returns_none(db_session):
    record_chat_message(
        db_session,
        role="assistant",
        content="识别播报",
        batch_id="batch-1",
        kind="recognition",
        food_summary_json="不是 json",
        now_utc=NOW,
    )
    assert find_open_batch(db_session, now_utc=NOW) is None


# ---------------------------------------------------------------------------
# recap_batch_status
# ---------------------------------------------------------------------------

_MIXED_ITEMS = [
    BatchItemStatus(food_name="熟鸡胸肉", quantity=150, state="confirmed", kcal=247.5),
    BatchItemStatus(food_name="白米饭", quantity=200, state="abandoned"),
]


@pytest.mark.asyncio
async def test_recap_uses_llm_summary_and_reuses_batch_id(db_session):
    client = StubLlmClient(
        [LlmJsonResult(ok=True, parsed={"summary": "已记录熟鸡胸肉150g,其余已放弃"})]
    )
    message = await recap_batch_status(
        db_session, client, "batch-1", "lunch", _MIXED_ITEMS, now_utc=NOW
    )

    assert message.content == "已记录熟鸡胸肉150g,其余已放弃"
    assert message.batch_id == "batch-1"
    assert message.kind == "recap"
    assert message.role == "assistant"
    assert message.date == "2026-08-24"

    # prompt 只带终态列表,不带对话历史/今日明细
    _, user_prompt = client.calls[0]
    assert "熟鸡胸肉" in user_prompt and "已记录" in user_prompt
    assert "白米饭" in user_prompt and "已放弃" in user_prompt
    assert "今日对话记录" not in user_prompt


@pytest.mark.asyncio
async def test_recap_llm_failure_falls_back_to_deterministic_text(db_session):
    client = StubLlmClient([_network_failure()])
    message = await recap_batch_status(
        db_session, client, "batch-1", "lunch", _MIXED_ITEMS, now_utc=NOW
    )

    assert "熟鸡胸肉150g" in message.content
    assert "白米饭200g" in message.content
    assert message.kind == "recap"


@pytest.mark.asyncio
async def test_recap_malformed_llm_payload_falls_back(db_session):
    client = StubLlmClient([LlmJsonResult(ok=True, parsed={"not_summary": "x"})])
    message = await recap_batch_status(
        db_session, client, "batch-1", "lunch", _MIXED_ITEMS, now_utc=NOW
    )

    assert "已记录" in message.content
    assert message.kind == "recap"
