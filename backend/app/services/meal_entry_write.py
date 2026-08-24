"""餐次明细写入/查询/删除(1.9,SPEC §7.4/§7.6)。

幂等写入是本步的关键正确性保证:`confirmation_id` 由后端在识别出该项那一刻签发、
贯穿这一项的整个生命周期;应用层先查后插做第一道防线,`confirmation_id` 上的唯一
索引是数据库层最后一道防线——并发重试撞上唯一索引冲突时捕获 IntegrityError 并优雅
返回已有记录,不向上抛异常(tasks/current.md"幂等写入")。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import MEAL_SLOT_VALUES
from app.models.meal_entry import MealEntry
from app.schemas.food_estimate import ConfirmationPreview
from app.services.attribution import attribution_date, utc_now_iso


class UntrustedNutritionError(Exception):
    """未拿到可信营养结果(kcal 为 null)时拒绝写入 meal_entry(SPEC §7.6/AGENTS.md 铁律)。"""


def _find_existing(db: Session, confirmation_id: str) -> MealEntry | None:
    """应用层幂等预检。独立成函数是为了让测试能模拟"预检没看到、插入才撞唯一索引"
    的并发场景(IntegrityError 兜底路径),不代表这层检查可省略。"""
    return db.query(MealEntry).filter_by(confirmation_id=confirmation_id).one_or_none()


def confirm_meal_entry(
    db: Session,
    preview: ConfirmationPreview,
    confirmation_id: str,
    *,
    now_utc: datetime,
) -> MealEntry:
    """幂等确认写入。`now_utc` 是这次批量确认动作的统一时刻(由前端生成、同一批共享),
    用来算这一行的归属日——后端不自己读当前时刻(批次归属日一致性)。

    幂等语义:同一个 confirmation_id 只会真正插入一行。命中已有记录直接返回(重放
    请求不再重新校验 kcal——当年写入时校验已通过);首次见到这个 id 且 kcal 为 null
    才拒绝。
    """
    existing = _find_existing(db, confirmation_id)
    if existing is not None:
        return existing

    if preview.nutrients.kcal is None:
        raise UntrustedNutritionError(
            f"{preview.food_name}: kcal 缺失,未拿到可信营养结果,拒绝写入(SPEC §7.6)"
        )

    entry = MealEntry(
        confirmation_id=confirmation_id,
        date=attribution_date(now_utc),
        meal_slot=preview.meal_slot,
        food_name=preview.food_name,
        quantity=preview.quantity,
        unit=preview.unit,
        kcal=preview.nutrients.kcal,
        carb_g=preview.nutrients.carb_g,
        protein_g=preview.nutrients.protein_g,
        fat_g=preview.nutrients.fat_g,
        fiber_g=preview.nutrients.fiber_g,
        source_tag=preview.source_tag,
        created_at=utc_now_iso(now_utc),
    )
    try:
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError:
        # 并发的真实网络重试:两次插入几乎同时发生,输掉的那次在这里兜底返回已有记录
        db.rollback()
        return db.query(MealEntry).filter_by(confirmation_id=confirmation_id).one()


def list_today_meal_entries(db: Session, *, now_utc: datetime | None = None) -> list[MealEntry]:
    """当前归属日全部明细,按 MEAL_SLOT_VALUES 顺序分组、组内按 id。两个用途:
    ①今日明细查询 API;②chat_turn 里给 LLM 当 today_context。"""
    today = attribution_date(now_utc)
    entries = db.query(MealEntry).filter(MealEntry.date == today).order_by(MealEntry.id).all()
    slot_order = {slot: index for index, slot in enumerate(MEAL_SLOT_VALUES)}
    return sorted(entries, key=lambda e: (slot_order[e.meal_slot], e.id))


def delete_todays_meal_entry(
    db: Session, entry_id: int, *, now_utc: datetime | None = None
) -> bool:
    """找不到,或该行不属于当前归属日 → False(历史日期的删除是 6.2 补录范围,本步不做)。"""
    entry = db.get(MealEntry, entry_id)
    if entry is None or entry.date != attribution_date(now_utc):
        return False
    db.delete(entry)
    db.commit()
    return True
