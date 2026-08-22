"""§7.2 Demo 分支(LLM 直接估算每 100g 营养)+ §7.4 确认预览(1.7)。

`estimate_food`:单个食物一次 LLM 调用,产出 per-100g 五项营养 + 置信度。JSON 合法但
不满足契约(缺字段、confidence 不合法、kcal 全 null 等)时自动重试一次,重试后仍失败
才对外报 invalid_model_output。

`estimate_items`:对一批已解析食物并发调用 `estimate_food`,内部用 1.6 的
`compute_nutrient_snapshot` 算出实际摄入营养,组装成 `ConfirmationPreview`——不含
date/created_at,那两个由 1.9 在 Confirm 时才算。失败项不静默丢弃,也不阻塞同批其他项
(并发限流在 llm_client.DashScopeClient 内部做,这里不用另加信号量)。
"""

from __future__ import annotations

import asyncio

from pydantic import ValidationError

from app.schemas.diet_parse import ParsedFoodItem, PreparationState
from app.schemas.food_estimate import ConfirmationPreview, FoodEstimate, ItemEstimateOutcome
from app.schemas.llm_outcome import LlmOutcome
from app.schemas.nutrition import NutrientPer100g
from app.services.llm_client import LlmClient
from app.services.nutrition_calc import compute_nutrient_snapshot

_PREPARATION_STATE_LABELS = {
    "raw": "raw(生,按烹饪前重量估算)",
    "cooked": "cooked(熟,按烹饪后重量估算)",
    "ready_to_consume": "ready_to_consume(即食/即饮成品,如牛奶、酸奶、面包、蛋糕、"
    "奶酪、饮料、罐头食品,按食物到手/到嘴时的实际状态估算,不用考虑生熟换算)",
}

_SYSTEM_PROMPT = """你是一个食物营养估算助手。给你一个食物名称和它的状态标签,你要凭常识
估算这个食物"每 100g 可食部"的营养值,只输出一个合法的 json 对象,不要输出任何其他文字。

输出结构固定为:
{"kcal_100g": 数字或null, "carb_100g": 数字或null, "protein_100g": 数字或null,
 "fat_100g": 数字或null, "fiber_100g": 数字或null,
 "confidence": "low"|"medium"|"high", "confidence_reason": "简短说明置信度依据"}

规则:
- 五项营养值单位都是"每 100g 可食部"多少克(热量是 kcal)。确实无法给出某一项估计时,
  该项填 null,不要用 0 顶替"不知道"(0 表示确定为零,和"不知道"是两回事)。
- kcal_100g 尽量给出估计值,这是最基础的一项,除非这个食物名称完全无法理解;其余四项
  (碳水/蛋白质/脂肪/膳食纤维)可以有把握的才给,没把握的填 null。
- confidence 反映你对这次估算的整体把握程度;confidence_reason 用一句话说明依据或不确定
  的原因(比如"常见食材,营养成分公开数据稳定" / "复合菜肴,配料和做法差异大,估算仅供参考")。
"""


def _build_estimate(parsed: object) -> FoodEstimate:
    if not isinstance(parsed, dict):
        raise ValueError("响应顶层不是 JSON 对象")

    nutrients = NutrientPer100g(
        kcal_100g=parsed.get("kcal_100g"),
        carb_100g=parsed.get("carb_100g"),
        protein_100g=parsed.get("protein_100g"),
        fat_100g=parsed.get("fat_100g"),
        fiber_100g=parsed.get("fiber_100g"),
    )
    confidence = parsed.get("confidence")
    confidence_reason = parsed.get("confidence_reason")
    if confidence not in ("low", "medium", "high"):
        raise ValueError(f"confidence 不是合法值: {confidence!r}")
    if not isinstance(confidence_reason, str) or not confidence_reason.strip():
        raise ValueError("confidence_reason 缺失或为空")

    return FoodEstimate(
        outcome=LlmOutcome.RESOLVED,
        nutrients=nutrients,
        confidence=confidence,
        confidence_reason=confidence_reason,
    )


async def estimate_food(
    client: LlmClient, food_name: str, preparation_state: PreparationState
) -> FoodEstimate:
    state_label = _PREPARATION_STATE_LABELS[preparation_state]
    user_prompt = f'食物名称:"{food_name}";状态:{state_label}'

    last_contract_error = ""
    for attempt in range(2):  # 首次 + 一次自动重试
        llm_result = await client.chat_json(system=_SYSTEM_PROMPT, user=user_prompt)

        if not llm_result.ok:
            if llm_result.error_kind == "response_not_json":
                last_contract_error = llm_result.error_detail or "响应不是合法 JSON"
                if attempt == 0:
                    continue
                return FoodEstimate(
                    outcome=LlmOutcome.INVALID_MODEL_OUTPUT,
                    message=f"模型响应格式异常,重试后仍失败:{last_contract_error}",
                )
            return FoodEstimate(
                outcome=LlmOutcome.SERVICE_UNAVAILABLE,
                message="AI 服务暂时不可用,请稍后再试",
            )

        try:
            return _build_estimate(llm_result.parsed)
        except (ValueError, TypeError, ValidationError) as exc:
            last_contract_error = str(exc)
            if attempt == 0:
                continue
            return FoodEstimate(
                outcome=LlmOutcome.INVALID_MODEL_OUTPUT,
                message=f"模型响应不符合契约,重试后仍失败:{last_contract_error}",
            )

    raise AssertionError("unreachable: 循环内每条路径都应该 return")


async def estimate_items(
    client: LlmClient, items: list[ParsedFoodItem], meal_slot: str
) -> list[ItemEstimateOutcome]:
    """按 item 并发估算,失败项不丢弃、不阻塞其他项;返回顺序与输入 items 一一对应
    (asyncio.gather 按输入顺序返回结果,不是按完成顺序)。"""

    async def _one(item: ParsedFoodItem) -> ItemEstimateOutcome:
        estimate = await estimate_food(client, item.food_name, item.preparation_state)
        if estimate.outcome != LlmOutcome.RESOLVED:
            return ItemEstimateOutcome(
                parsed_item=item, outcome=estimate.outcome, message=estimate.message
            )

        assert estimate.nutrients is not None  # resolved 时 FoodEstimate 已保证非空
        snapshot = compute_nutrient_snapshot(estimate.nutrients, item.quantity)
        preview = ConfirmationPreview(
            food_name=item.food_name,
            quantity=item.quantity,
            unit=item.unit,
            meal_slot=meal_slot,
            nutrients=snapshot,
            source_tag="llm_estimate",
            confidence=estimate.confidence,
            confidence_reason=estimate.confidence_reason,
        )
        return ItemEstimateOutcome(parsed_item=item, outcome=LlmOutcome.RESOLVED, preview=preview)

    return list(await asyncio.gather(*(_one(item) for item in items)))
