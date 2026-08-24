"""1.9 餐次明细路由的请求/响应契约(tasks/current.md"二、后端 API 路由")。

`preview` 复用 1.7 的 `ConfirmationPreview` 原 schema 不改动;`now_utc` 是这次批量
确认动作的统一时刻——同一批的每个 `POST /meal-entries` 都携带同一个值,保证网络排队
不会把同一次点击写进两个归属日(批次归属日一致性)。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import MealSlot, SourceTag, Unit
from app.schemas.food_estimate import ConfirmationPreview


class ConfirmMealEntryRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    preview: ConfirmationPreview
    now_utc: datetime

    @field_validator("now_utc")
    @classmethod
    def _validate_now_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("now_utc 必须是 tz-aware 的 UTC 时刻(如 2026-08-24T03:00:00Z)")
        return value


class MealEntryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    confirmation_id: str
    date: str
    meal_slot: MealSlot
    food_name: str
    quantity: float
    unit: Unit
    kcal: float | None = None
    carb_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    source_tag: SourceTag
    created_at: str
