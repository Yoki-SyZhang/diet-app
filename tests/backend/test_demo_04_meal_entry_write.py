"""1.9 今日明细查询/删除:归属日过滤(不是滚动 24 小时窗口)、餐次分组排序、
防御性拒绝(找不到/非今日 → False)。幂等相关测试在
`test_demo_04_meal_entry_idempotency.py` 单独成文件。
"""

from datetime import datetime, timezone

from sqlalchemy import func

from app.models.meal_entry import MealEntry
from app.schemas.food_estimate import ConfirmationPreview
from app.schemas.nutrition import NutrientSet
from app.services.meal_entry_write import (
    confirm_meal_entry,
    delete_todays_meal_entry,
    list_today_meal_entries,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)  # 上海本地 20:00,归 2026-08-24
YESTERDAY_NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)  # 归 2026-08-23


def _preview(food_name="熟鸡胸肉", meal_slot="lunch") -> ConfirmationPreview:
    return ConfirmationPreview(
        food_name=food_name,
        quantity=150,
        unit="g",
        meal_slot=meal_slot,
        nutrients=NutrientSet(kcal=200.0),
        source_tag="llm_estimate",
        confidence="medium",
        confidence_reason="常见食物,估算依据充分",
    )


def test_list_today_filters_by_attribution_date(db_session):
    confirm_meal_entry(db_session, _preview("昨天的饭"), "c-old", now_utc=YESTERDAY_NOW)
    confirm_meal_entry(db_session, _preview("今天的饭"), "c-new", now_utc=NOW)

    todays = list_today_meal_entries(db_session, now_utc=NOW)

    assert [e.food_name for e in todays] == ["今天的饭"]


def test_list_today_orders_by_meal_slot_then_id(db_session):
    confirm_meal_entry(db_session, _preview("晚饭菜", "dinner"), "c-1", now_utc=NOW)
    confirm_meal_entry(db_session, _preview("早饭菜", "breakfast"), "c-2", now_utc=NOW)
    confirm_meal_entry(db_session, _preview("加餐", "other"), "c-3", now_utc=NOW)
    confirm_meal_entry(db_session, _preview("午饭菜A", "lunch"), "c-4", now_utc=NOW)
    confirm_meal_entry(db_session, _preview("午饭菜B", "lunch"), "c-5", now_utc=NOW)

    todays = list_today_meal_entries(db_session, now_utc=NOW)

    assert [e.food_name for e in todays] == ["早饭菜", "午饭菜A", "午饭菜B", "晚饭菜", "加餐"]


def test_list_today_empty_when_no_entries(db_session):
    assert list_today_meal_entries(db_session, now_utc=NOW) == []


def test_delete_todays_entry_removes_row(db_session):
    entry = confirm_meal_entry(db_session, _preview(), "c-1", now_utc=NOW)

    assert delete_todays_meal_entry(db_session, entry.id, now_utc=NOW) is True
    assert db_session.query(func.count(MealEntry.id)).scalar() == 0


def test_delete_missing_entry_returns_false(db_session):
    assert delete_todays_meal_entry(db_session, 999, now_utc=NOW) is False


def test_delete_non_today_entry_refused(db_session):
    entry = confirm_meal_entry(db_session, _preview(), "c-old", now_utc=YESTERDAY_NOW)

    assert delete_todays_meal_entry(db_session, entry.id, now_utc=NOW) is False
    assert db_session.query(func.count(MealEntry.id)).scalar() == 1


def test_delete_does_not_affect_other_rows(db_session):
    keep = confirm_meal_entry(db_session, _preview("保留"), "c-keep", now_utc=NOW)
    doomed = confirm_meal_entry(db_session, _preview("删除"), "c-del", now_utc=NOW)

    assert delete_todays_meal_entry(db_session, doomed.id, now_utc=NOW) is True
    remaining = list_today_meal_entries(db_session, now_utc=NOW)
    assert [e.id for e in remaining] == [keep.id]
