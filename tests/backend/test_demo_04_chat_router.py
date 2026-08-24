"""1.9 对话路由集成测试(真实迁移库 + stub LLM):POST /chat/messages 各分支、
/modify 成功失败、/recap 正常与 LLM 失败兜底、/today、/open-batch、空文本 422。
"""

import json
from datetime import datetime, timezone

import pytest

from app.schemas.chat import ConfirmableItem
from app.schemas.diet_parse import ParsedFoodItem
from app.schemas.food_estimate import ConfirmationPreview, ItemEstimateOutcome
from app.schemas.llm_outcome import LlmOutcome
from app.schemas.nutrition import NutrientSet
from app.services.chat import record_chat_message
from app.services.llm_client import LlmJsonResult

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class StubLlmClient:
    def __init__(self, results: list[LlmJsonResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, *, system: str, user: str, temperature: float = 0.0):
        self.calls.append((system, user))
        return self._results.pop(0)


def _parse_resolved(items=None, meal_slot="lunch") -> LlmJsonResult:
    if items is None:
        items = [
            {"food_name": "熟鸡胸肉", "quantity": 150, "unit": "g", "preparation_state": "cooked"}
        ]
    return LlmJsonResult(
        ok=True,
        parsed={
            "intent": "new_entry",
            "status": "resolved",
            "meal_slot": meal_slot,
            "items": items,
        },
    )


def _estimate_ok() -> LlmJsonResult:
    return LlmJsonResult(
        ok=True,
        parsed={
            "kcal_100g": 165,
            "carb_100g": 0,
            "protein_100g": 31,
            "fat_100g": 3.6,
            "fiber_100g": None,
            "confidence": "high",
            "confidence_reason": "常见食材,营养数据稳定",
        },
    )


def _confirmable(confirmation_id="conf-1", food_name="熟鸡胸肉") -> ConfirmableItem:
    return ConfirmableItem(
        confirmation_id=confirmation_id,
        outcome=ItemEstimateOutcome(
            parsed_item=ParsedFoodItem(
                food_name=food_name, quantity=150, unit="g", preparation_state="cooked"
            ),
            outcome=LlmOutcome.RESOLVED,
            preview=ConfirmationPreview(
                food_name=food_name,
                quantity=150,
                unit="g",
                meal_slot="lunch",
                nutrients=NutrientSet(kcal=247.5),
                source_tag="llm_estimate",
                confidence="high",
                confidence_reason="常见食材,营养数据稳定",
            ),
        ),
    )


class TestPostMessage:
    def test_no_log_intent_branch(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient(
                [LlmJsonResult(ok=True, parsed={"intent": "no_log_intent", "message": "你好呀"})]
            )
        )
        resp = migrated_client.client.post("/chat/messages", json={"text": "早上好"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "no_log_intent"
        assert body["outcome"] is None
        assert body["batch_id"] is None
        assert body["items"] == []
        assert body["user_message"]["content"] == "早上好"
        assert body["assistant_message"]["content"] == "你好呀"

    def test_edit_existing_entry_branch(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient(
                [
                    LlmJsonResult(
                        ok=True,
                        parsed={"intent": "edit_existing_entry", "message": "暂不支持修改已有记录"},
                    )
                ]
            )
        )
        resp = migrated_client.client.post("/chat/messages", json={"text": "改掉昨天的记录"})

        assert resp.status_code == 200
        assert resp.json()["intent"] == "edit_existing_entry"
        assert resp.json()["outcome"] is None

    def test_needs_clarification_branch(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient(
                [
                    LlmJsonResult(
                        ok=True,
                        parsed={
                            "intent": "new_entry",
                            "status": "needs_clarification",
                            "message": "大概多少克?",
                        },
                    )
                ]
            )
        )
        resp = migrated_client.client.post("/chat/messages", json={"text": "我吃了鸡胸肉"})

        body = resp.json()
        assert body["outcome"] == "needs_clarification"
        assert body["batch_id"] is None

    def test_service_unavailable_branch(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient([LlmJsonResult(ok=False, error_kind="network", error_detail="超时")])
        )
        resp = migrated_client.client.post("/chat/messages", json={"text": "我吃了150g熟鸡胸肉"})

        assert resp.json()["outcome"] == "service_unavailable"

    def test_resolved_returns_card_items_with_signed_ids(self, migrated_client):
        migrated_client.use_llm(StubLlmClient([_parse_resolved(), _estimate_ok()]))
        resp = migrated_client.client.post(
            "/chat/messages", json={"text": "午饭吃了150g熟鸡胸肉"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] == "resolved"
        assert body["batch_id"]
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["confirmation_id"]
        assert item["outcome"]["preview"]["food_name"] == "熟鸡胸肉"
        assert item["outcome"]["preview"]["nutrients"]["kcal"] == 247.5
        assert body["assistant_message"]["kind"] == "recognition"
        assert body["assistant_message"]["batch_id"] == body["batch_id"]

    def test_empty_text_rejected_422(self, migrated_client):
        resp = migrated_client.client.post("/chat/messages", json={"text": ""})
        assert resp.status_code == 422


class TestModify:
    def test_modify_success(self, migrated_client):
        corrected = [
            {"food_name": "熟鸡胸肉", "quantity": 200, "unit": "g", "preparation_state": "cooked"}
        ]
        migrated_client.use_llm(
            StubLlmClient(
                [
                    LlmJsonResult(
                        ok=True,
                        parsed={
                            "intent": "correct_pending_item",
                            "status": "resolved",
                            "meal_slot": "lunch",
                            "items": corrected,
                        },
                    ),
                    _estimate_ok(),
                ]
            )
        )
        resp = migrated_client.client.post(
            "/chat/messages/modify",
            json={
                "confirmation_id": "conf-1",
                "original_item": {
                    "food_name": "熟鸡胸肉",
                    "quantity": 100,
                    "unit": "g",
                    "preparation_state": "cooked",
                },
                "meal_slot": "lunch",
                "correction_text": "改成200g",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["confirmation_id"] == "conf-1"
        assert body["outcome"]["preview"]["quantity"] == 200
        assert body["failure_reason"] is None

    def test_modify_failure(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient(
                [
                    LlmJsonResult(
                        ok=True,
                        parsed={
                            "intent": "correct_pending_item",
                            "status": "needs_clarification",
                            "message": "想改成多少克?",
                        },
                    )
                ]
            )
        )
        resp = migrated_client.client.post(
            "/chat/messages/modify",
            json={
                "confirmation_id": "conf-1",
                "original_item": {
                    "food_name": "熟鸡胸肉",
                    "quantity": 100,
                    "unit": "g",
                    "preparation_state": "cooked",
                },
                "meal_slot": "lunch",
                "correction_text": "量不对",
            },
        )

        body = resp.json()
        assert body["success"] is False
        assert body["outcome"] is None
        assert body["failure_reason"] == "想改成多少克?"


class TestRecap:
    _payload = {
        "batch_id": "batch-1",
        "meal_slot": "lunch",
        "items": [
            {"food_name": "熟鸡胸肉", "quantity": 150, "state": "confirmed", "kcal": 247.5},
            {"food_name": "白米饭", "quantity": 200, "state": "abandoned"},
        ],
        "now_utc": "2026-08-24T12:00:00Z",
    }

    def test_recap_normal(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient([LlmJsonResult(ok=True, parsed={"summary": "已记录熟鸡胸肉150g"})])
        )
        resp = migrated_client.client.post("/chat/messages/recap", json=self._payload)

        assert resp.status_code == 200
        message = resp.json()["assistant_message"]
        assert message["content"] == "已记录熟鸡胸肉150g"
        assert message["kind"] == "recap"
        assert message["batch_id"] == "batch-1"

    def test_recap_llm_failure_falls_back(self, migrated_client):
        migrated_client.use_llm(
            StubLlmClient([LlmJsonResult(ok=False, error_kind="network", error_detail="超时")])
        )
        resp = migrated_client.client.post("/chat/messages/recap", json=self._payload)

        assert resp.status_code == 200
        assert "熟鸡胸肉150g" in resp.json()["assistant_message"]["content"]

    def test_recap_naive_now_utc_rejected(self, migrated_client):
        payload = dict(self._payload, now_utc="2026-08-24T12:00:00")
        resp = migrated_client.client.post("/chat/messages/recap", json=payload)
        assert resp.status_code == 422


class TestTodayAndOpenBatch:
    def test_today_lists_messages(self, migrated_client):
        with migrated_client.session_factory() as db:
            record_chat_message(db, role="user", content="第一句")
            record_chat_message(db, role="assistant", content="第二句")

        resp = migrated_client.client.get("/chat/messages/today")

        assert resp.status_code == 200
        assert [m["content"] for m in resp.json()] == ["第一句", "第二句"]

    def test_open_batch_none(self, migrated_client):
        resp = migrated_client.client.get("/chat/messages/open-batch")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_open_batch_present(self, migrated_client):
        item = _confirmable("conf-1")
        with migrated_client.session_factory() as db:
            record_chat_message(
                db,
                role="assistant",
                content="识别播报",
                batch_id="batch-1",
                kind="recognition",
                food_summary_json=json.dumps([item.model_dump(mode="json")], ensure_ascii=False),
            )

        resp = migrated_client.client.get("/chat/messages/open-batch")

        assert resp.status_code == 200
        body = resp.json()
        assert body["batch_id"] == "batch-1"
        assert [i["confirmation_id"] for i in body["items"]] == ["conf-1"]
