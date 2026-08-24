"""1.9 餐次明细路由集成测试(真实迁移库):POST(含幂等重复场景)/GET/DELETE 的
正常与异常路径。

`now_utc` 默认用测试运行时的真实当前时刻——`GET /meal-entries/today` 按服务器当前
归属日过滤,POST 的归属日必须与之一致,测试才不依赖"今天是哪天"。只有断言具体
date 值的用例才用固定时刻。
"""

from datetime import datetime, timezone

from sqlalchemy import func, text

from app.models.meal_entry import MealEntry


def _confirm_payload(confirmation_id="conf-1", food_name="熟鸡胸肉", kcal=247.5, now_utc=None):
    return {
        "confirmation_id": confirmation_id,
        "preview": {
            "food_name": food_name,
            "quantity": 150,
            "unit": "g",
            "meal_slot": "lunch",
            "nutrients": {
                "kcal": kcal,
                "carb_g": 0,
                "protein_g": 46.5,
                "fat_g": 5.3,
                "fiber_g": None,
            },
            "source_tag": "llm_estimate",
            "confidence": "high",
            "confidence_reason": "常见食材,营养数据稳定",
        },
        "now_utc": now_utc or datetime.now(timezone.utc).isoformat(),
    }


def _row_count(migrated_client) -> int:
    with migrated_client.session_factory() as db:
        return db.query(func.count(MealEntry.id)).scalar()


class TestPost:
    def test_post_creates_entry_201(self, migrated_client):
        fixed_now = "2026-08-24T12:00:00Z"
        resp = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload(now_utc=fixed_now)
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["confirmation_id"] == "conf-1"
        assert body["date"] == "2026-08-24"  # 上海本地 20:00 → 归 2026-08-24
        assert body["food_name"] == "熟鸡胸肉"
        assert body["kcal"] == 247.5
        assert body["fiber_g"] is None
        assert body["source_tag"] == "llm_estimate"
        assert body["created_at"] == "2026-08-24T12:00:00+00:00"

    def test_duplicate_post_same_confirmation_id_still_201_but_single_row(
        self, migrated_client
    ):
        first = migrated_client.client.post("/meal-entries", json=_confirm_payload())
        second = migrated_client.client.post("/meal-entries", json=_confirm_payload())

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert _row_count(migrated_client) == 1

    def test_kcal_null_rejected_422(self, migrated_client):
        resp = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload(kcal=None)
        )

        assert resp.status_code == 422
        assert _row_count(migrated_client) == 0

    def test_naive_now_utc_rejected_422(self, migrated_client):
        payload = _confirm_payload()
        payload["now_utc"] = "2026-08-24T12:00:00"
        resp = migrated_client.client.post("/meal-entries", json=payload)

        assert resp.status_code == 422

    def test_missing_confirmation_id_rejected_422(self, migrated_client):
        payload = _confirm_payload()
        del payload["confirmation_id"]
        resp = migrated_client.client.post("/meal-entries", json=payload)

        assert resp.status_code == 422


class TestGetToday:
    def test_lists_today_entries(self, migrated_client):
        migrated_client.client.post("/meal-entries", json=_confirm_payload("conf-1", "熟鸡胸肉"))
        migrated_client.client.post("/meal-entries", json=_confirm_payload("conf-2", "白米饭"))

        resp = migrated_client.client.get("/meal-entries/today")

        assert resp.status_code == 200
        assert {e["food_name"] for e in resp.json()} == {"熟鸡胸肉", "白米饭"}

    def test_excludes_other_days(self, migrated_client):
        migrated_client.client.post("/meal-entries", json=_confirm_payload())
        with migrated_client.session_factory() as db:
            db.execute(
                text(
                    "UPDATE meal_entry SET date = '2000-01-01' WHERE confirmation_id = 'conf-1'"
                )
            )
            db.commit()

        resp = migrated_client.client.get("/meal-entries/today")

        assert resp.json() == []


class TestDelete:
    def test_delete_today_entry_204(self, migrated_client):
        entry_id = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload()
        ).json()["id"]

        resp = migrated_client.client.delete(f"/meal-entries/{entry_id}")

        assert resp.status_code == 204
        assert _row_count(migrated_client) == 0

    def test_delete_missing_404(self, migrated_client):
        resp = migrated_client.client.delete("/meal-entries/999")
        assert resp.status_code == 404

    def test_delete_non_today_404(self, migrated_client):
        entry_id = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload()
        ).json()["id"]
        with migrated_client.session_factory() as db:
            db.execute(text("UPDATE meal_entry SET date = '2000-01-01'"))
            db.commit()

        resp = migrated_client.client.delete(f"/meal-entries/{entry_id}")

        assert resp.status_code == 404
        assert _row_count(migrated_client) == 1

    def test_delete_only_removes_target_row(self, migrated_client):
        keep = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload("conf-keep", "保留")
        ).json()["id"]
        doomed = migrated_client.client.post(
            "/meal-entries", json=_confirm_payload("conf-del", "删除")
        ).json()["id"]

        assert migrated_client.client.delete(f"/meal-entries/{doomed}").status_code == 204
        remaining = migrated_client.client.get("/meal-entries/today").json()
        assert [e["id"] for e in remaining] == [keep]
