"""§7.2 Demo 分支(LLM 直接估算 per-100g 营养)+ §7.4 确认预览契约(1.7)。

`ConfirmationPreview` 是 1.6-1.8 这个 PR 的终态产出,**不含 `date`/`created_at`**——
这两个值必须是"用户点 Confirm 那一刻"的归属日/UTC 时间戳,预览生成阶段提前算会不准,
由 1.9 在 Confirm 时统一计算(tasks/current.md 关键设计取舍 2)。`source_tag` 复用完整
`SOURCE_TAG_VALUES` 而不是写死 `Literal["llm_estimate"]`,方便 Closed Beta 换上四级
查询链时这个形状可以直接复用。
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MealSlot, SourceTag
from app.schemas.diet_parse import ParsedFoodItem
from app.schemas.llm_outcome import LlmOutcome
from app.schemas.nutrition import NutrientPer100g, NutrientSet

Confidence = Literal["low", "medium", "high"]


class FoodEstimate(BaseModel):
    """单个食物一次 LLM 估算的结果(四态)。`outcome=resolved` 时 `kcal_100g` 必须
    非空——五项营养全为 null 不算"拿到可信营养结果"(AGENTS.md 铁律),也没法进 A1
    热量趋势;其余四项营养素允许 null。"""

    outcome: LlmOutcome
    nutrients: NutrientPer100g | None = None
    confidence: Confidence | None = None
    confidence_reason: str | None = Field(default=None, min_length=1)
    message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_outcome_consistency(self) -> "FoodEstimate":
        if self.outcome == LlmOutcome.RESOLVED:
            if self.nutrients is None:
                raise ValueError("outcome=resolved 时 nutrients 必须提供")
            if self.nutrients.kcal_100g is None:
                raise ValueError("outcome=resolved 时 kcal_100g 必须非空(AGENTS.md 铁律)")
            if self.confidence is None:
                raise ValueError("outcome=resolved 时 confidence 必须提供")
            if not self.confidence_reason:
                raise ValueError("outcome=resolved 时 confidence_reason 必须提供")
            if self.message is not None:
                raise ValueError("outcome=resolved 时 message 必须为 None")
        else:
            if self.nutrients is not None:
                raise ValueError(f"outcome={self.outcome} 时 nutrients 必须为 None")
            if self.confidence is not None:
                raise ValueError(f"outcome={self.outcome} 时 confidence 必须为 None")
            if not self.message:
                raise ValueError(f"outcome={self.outcome} 时 message 必须非空")
        return self


class ConfirmationPreview(BaseModel):
    food_name: str = Field(min_length=1)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal["g"]
    meal_slot: MealSlot
    nutrients: NutrientSet
    source_tag: SourceTag
    confidence: Confidence
    confidence_reason: str = Field(min_length=1)
    warning: Literal["可能不准"] = "可能不准"


class ItemEstimateOutcome(BaseModel):
    """`estimate_items` 的逐项结果,失败项不静默丢弃——顺序与输入 items 一一对应。"""

    parsed_item: ParsedFoodItem
    outcome: LlmOutcome
    preview: ConfirmationPreview | None = None
    message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_outcome_consistency(self) -> "ItemEstimateOutcome":
        if self.outcome == LlmOutcome.RESOLVED:
            if self.preview is None:
                raise ValueError("outcome=resolved 时 preview 必须提供")
            if self.message is not None:
                raise ValueError("outcome=resolved 时 message 必须为 None")
        else:
            if self.preview is not None:
                raise ValueError(f"outcome={self.outcome} 时 preview 必须为 None")
            if not self.message:
                raise ValueError(f"outcome={self.outcome} 时 message 必须非空")
        return self
