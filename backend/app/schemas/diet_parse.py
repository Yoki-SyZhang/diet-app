"""§8.1 自然语言饮食解析契约(1.8)。Demo 阶段只产出 `unit="g"`(§7.1:serving 只在
命中个人常吃食谱时合法,`food_favorite` 是 MVP 才建的表)。

`preparation_state` 三选一(SPEC §7.1):
- `raw`/`cooked`:生重/熟重会明显影响每 100g 营养口径,原型食材裸词没有生熟线索时,
  nl_parse 直接判 needs_clarification,不猜。
- `ready_to_consume`:食物本身已是可直接食用/饮用的成品,生熟区分对这次营养匹配没有
  实际意义(牛奶、酸奶、面包、蛋糕、奶酪、饮料、罐头食品等),不触发生熟追问,也不等于
  `recipe`(`recipe` 专指常吃库保存的固定配方,当前 Demo 不涉及)。
不会有 `unknown` 流到这一层——`unknown` 保留给"确实无法判断"的语义,不能借它表示
"这个食物不适用生熟区分",那种情况用 `ready_to_consume`(tasks/current.md 关键设计
取舍 5)。
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MealSlot
from app.schemas.llm_outcome import LlmOutcome

PreparationState = Literal["raw", "cooked", "ready_to_consume"]


class ParsedFoodItem(BaseModel):
    food_name: str = Field(min_length=1)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal["g"]
    preparation_state: PreparationState


class DietParseResult(BaseModel):
    """四态结果(见 `app.schemas.llm_outcome.LlmOutcome`)。`outcome=resolved` 时
    `meal_slot`/`items` 必须非空且 `message` 为 None;其余三态相反——`items` 必须为空,
    `message` 必须非空。"""

    outcome: LlmOutcome
    meal_slot: MealSlot | None = None
    items: list[ParsedFoodItem] = Field(default_factory=list)
    message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_outcome_consistency(self) -> "DietParseResult":
        if self.outcome == LlmOutcome.RESOLVED:
            if not self.items:
                raise ValueError("outcome=resolved 时 items 不能为空")
            if self.meal_slot is None:
                raise ValueError("outcome=resolved 时 meal_slot 必须提供")
            if self.message is not None:
                raise ValueError("outcome=resolved 时 message 必须为 None")
        else:
            if self.items:
                raise ValueError(f"outcome={self.outcome} 时 items 必须为空")
            if self.message is None:
                raise ValueError(f"outcome={self.outcome} 时 message 必须非空")
        return self
