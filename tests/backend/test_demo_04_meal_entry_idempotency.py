"""1.9 幂等写入(本步的关键正确性保证,单独成文件):同一 `confirmation_id` 不管重试
几次只插入一行;数据库层唯一索引兜底的并发场景被优雅处理;`now_utc` 决定归属日;
kcal 缺失拒绝写入(SPEC §7.6),但重放已成功的请求不再重复校验。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func

import app.services.meal_entry_write as meal_entry_write
from app.models.meal_entry import MealEntry
from app.schemas.food_estimate import ConfirmationPreview
from app.schemas.nutrition import NutrientSet
from app.services.meal_entry_write import UntrustedNutritionError, confirm_meal_entry

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)  # 上海本地 20:00,归 2026-08-24


def _preview(**overrides) -> ConfirmationPreview:
    payload = {
        "food_name": "熟鸡胸肉",
        "quantity": 150,
        "unit": "g",
        "meal_slot": "lunch",
        "nutrients": NutrientSet(kcal=247.5, carb_g=0, protein_g=46.5, fat_g=5.3, fiber_g=None),
        "source_tag": "llm_estimate",
        "confidence": "medium",
        "confidence_reason": "常见食物,估算依据充分",
    }
    payload.update(overrides)
    return ConfirmationPreview(**payload)


def _count(db) -> int:
    return db.query(func.count(MealEntry.id)).scalar()


def test_same_confirmation_id_inserts_only_one_row(db_session):
    first = confirm_meal_entry(db_session, _preview(), "conf-1", now_utc=NOW)
    second = confirm_meal_entry(db_session, _preview(), "conf-1", now_utc=NOW)

    assert _count(db_session) == 1
    assert second.id == first.id
    assert second.confirmation_id == "conf-1"


def test_different_confirmation_ids_insert_two_rows(db_session):
    confirm_meal_entry(db_session, _preview(), "conf-1", now_utc=NOW)
    confirm_meal_entry(db_session, _preview(food_name="熟西兰花"), "conf-2", now_utc=NOW)

    assert _count(db_session) == 2


def test_written_row_carries_preview_snapshot_and_attribution(db_session):
    entry = confirm_meal_entry(db_session, _preview(), "conf-1", now_utc=NOW)

    assert entry.date == "2026-08-24"
    assert entry.meal_slot == "lunch"
    assert entry.food_name == "熟鸡胸肉"
    assert entry.quantity == 150
    assert entry.unit == "g"
    assert entry.kcal == 247.5
    assert entry.carb_g == 0  # 确定为零,不是缺失
    assert entry.fiber_g is None  # 缺失保持 null,不用 0 顶替
    assert entry.source_tag == "llm_estimate"
    assert entry.created_at == "2026-08-24T12:00:00+00:00"


def test_unique_index_conflict_returns_existing_without_raising(db_session, monkeypatch):
    """模拟真实并发重试:应用层预检没看到已有行(两次插入几乎同时),插入撞上唯一索引,
    应捕获 IntegrityError、rollback 后返回已有记录,不向上抛异常。"""
    confirm_meal_entry(db_session, _preview(), "conf-race", now_utc=NOW)

    # 让预检"看不到"已有行,强迫代码走插入→IntegrityError→兜底查询路径
    monkeypatch.setattr(meal_entry_write, "_find_existing", lambda db, cid: None)

    result = confirm_meal_entry(db_session, _preview(), "conf-race", now_utc=NOW)

    assert result.confirmation_id == "conf-race"
    assert _count(db_session) == 1


def test_different_now_utc_yields_different_attribution_dates(db_session):
    # 上海本地 2026-08-24 01:00(未过 02:00 切换点)→ 归 2026-08-23
    before_cutoff = datetime(2026, 8, 23, 17, 0, tzinfo=timezone.utc)
    entry_a = confirm_meal_entry(db_session, _preview(), "conf-a", now_utc=before_cutoff)
    entry_b = confirm_meal_entry(db_session, _preview(), "conf-b", now_utc=NOW)

    assert entry_a.date == "2026-08-23"
    assert entry_b.date == "2026-08-24"


def test_kcal_none_first_time_raises_and_writes_nothing(db_session):
    bad = _preview(nutrients=NutrientSet(kcal=None, carb_g=10))

    with pytest.raises(UntrustedNutritionError):
        confirm_meal_entry(db_session, bad, "conf-bad", now_utc=NOW)
    assert _count(db_session) == 0


def test_kcal_none_replay_after_success_returns_existing_without_revalidation(db_session):
    """重放已成功写入的请求:即使这次请求体上的 kcal 是 null(理论上不该发生,但网络
    重放可能携带任意历史内容),也直接返回旧记录——当年写入时校验已通过。"""
    first = confirm_meal_entry(db_session, _preview(), "conf-1", now_utc=NOW)
    replay = confirm_meal_entry(
        db_session,
        _preview(nutrients=NutrientSet(kcal=None)),
        "conf-1",
        now_utc=NOW,
    )

    assert replay.id == first.id
    assert replay.kcal == 247.5
    assert _count(db_session) == 1
