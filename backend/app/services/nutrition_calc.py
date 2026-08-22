"""Demo 阶段的单位与营养计算引擎(SPEC §7.3,1.6)。纯函数,不调 LLM、不做 I/O。

不做"总重→可食部克重"(可食率)换算——那个机制绑定在 food_base_cn 查询链路上
(SPEC §4.4.1/§7.1),Demo 阶段不查那张表,详见 tasks/current.md 关键设计取舍 4。
"""

from app.schemas.nutrition import NutrientPer100g, NutrientSet


def compute_nutrient_snapshot(per_100g: NutrientPer100g, quantity_g: float) -> NutrientSet:
    """quantity_g × per_100g / 100,任一 per_100g 字段为 None → 对应字段结果为 None
    (null 传播,不当 0,AGENTS.md 铁律)。"""

    def _scale(value: float | None) -> float | None:
        if value is None:
            return None
        return value * quantity_g / 100

    return NutrientSet(
        kcal=_scale(per_100g.kcal_100g),
        carb_g=_scale(per_100g.carb_100g),
        protein_g=_scale(per_100g.protein_100g),
        fat_g=_scale(per_100g.fat_100g),
        fiber_g=_scale(per_100g.fiber_100g),
    )
