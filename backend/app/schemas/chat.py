"""1.9 对话路由的请求/响应契约(tasks/current.md"二、后端 API 路由")。

`ConfirmableItem.outcome` 复用 1.7 的 `ItemEstimateOutcome` 原 schema 不改动;
`confirmation_id`/`batch_id` 都由后端在识别出结果那一刻签发,前端只原样携带。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import MealSlot
from app.schemas.diet_parse import Intent, ParsedFoodItem
from app.schemas.food_estimate import ItemEstimateOutcome
from app.schemas.llm_outcome import LlmOutcome

ChatRole = Literal["user", "assistant"]
ChatMessageKind = Literal["recognition", "recap"]


def _require_tz_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now_utc 必须是 tz-aware 的 UTC 时刻(如 2026-08-24T03:00:00Z)")
    return value


class ChatMessageIn(BaseModel):
    text: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    """对话气泡的展示字段。`food_summary_json` 是批次恢复的内部快照,不随消息列表
    下发——恢复走专门的 `GET /chat/messages/open-batch`。"""

    model_config = {"from_attributes": True}

    id: int
    date: str
    role: ChatRole
    content: str
    image_ref: str | None = None
    created_at: str
    batch_id: str | None = None
    kind: ChatMessageKind | None = None


class ConfirmableItem(BaseModel):
    confirmation_id: str = Field(min_length=1)
    outcome: ItemEstimateOutcome


class ChatTurnResponse(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    intent: Intent
    outcome: LlmOutcome | None = None
    batch_id: str | None = None  # 产出卡片时才有值
    items: list[ConfirmableItem] = Field(default_factory=list)  # 只含估算成功、进卡片的项

    @model_validator(mode="after")
    def _check_batch_consistency(self) -> "ChatTurnResponse":
        if (self.batch_id is None) != (not self.items):
            raise ValueError("batch_id 与 items 必须同时有值或同时为空")
        return self


class ModifyCorrectionRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    original_item: ParsedFoodItem
    meal_slot: MealSlot
    correction_text: str = Field(min_length=1)


class ModifyCorrectionResponse(BaseModel):
    confirmation_id: str
    success: bool
    outcome: ItemEstimateOutcome | None = None  # success 时有意义
    failure_reason: str | None = None  # 失败时有意义

    @model_validator(mode="after")
    def _check_success_consistency(self) -> "ModifyCorrectionResponse":
        if self.success:
            if self.outcome is None:
                raise ValueError("success=True 时 outcome 必须提供")
            if self.failure_reason is not None:
                raise ValueError("success=True 时 failure_reason 必须为 None")
        else:
            if self.outcome is not None:
                raise ValueError("success=False 时 outcome 必须为 None")
            if not self.failure_reason:
                raise ValueError("success=False 时 failure_reason 必须非空")
        return self


class BatchItemStatus(BaseModel):
    food_name: str = Field(min_length=1)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    state: Literal["confirmed", "abandoned"]
    kcal: float | None = None  # confirmed 时有意义


class RecapRequest(BaseModel):
    batch_id: str = Field(min_length=1)
    meal_slot: MealSlot
    items: list[BatchItemStatus] = Field(min_length=1)
    now_utc: datetime  # 这次批量动作的统一时刻(批次归属日一致性,tasks/current.md)

    @field_validator("now_utc")
    @classmethod
    def _validate_now_utc(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class RecapResponse(BaseModel):
    assistant_message: ChatMessageOut


class OpenBatchOut(BaseModel):
    batch_id: str
    items: list[ConfirmableItem] = Field(min_length=1)
