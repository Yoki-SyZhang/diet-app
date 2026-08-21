"""从 USDA FoodData Central 食物对象里按 id+name+unit 三重匹配提取 5 项营养(SPEC §4.4.2)。

纯提取逻辑,不碰文件/网络/数据库。两个数据集(Foundation/Survey)共用同一份能量优先级——
已用真实下载文件验证:Survey 里能量只出现 id=1008,Foundation 里 id=1008/2047 都会被
实际选中(id=2048 目前测不到会被选中的真实场景,纯防御性兜底),两者从不在同一条记录里
同时出现,所以"多个能量候选、只取一个不相加"的行为只能靠人工构造的 fixture 验证。
"""

from __future__ import annotations

from dataclasses import dataclass

# 依次尝试,命中第一个就停,绝不把多个能量候选相加
ENERGY_KCAL_IDS = (1008, 2047, 2048)
ENERGY_KCAL_NAME_BY_ID = {
    1008: "Energy",
    2047: "Energy (Atwater General Factors)",
    2048: "Energy (Atwater Specific Factors)",
}
ENERGY_KCAL_UNIT = "kcal"

PROTEIN_ID, PROTEIN_NAME, PROTEIN_UNIT = 1003, "Protein", "g"
FAT_ID, FAT_NAME, FAT_UNIT = 1004, "Total lipid (fat)", "g"
CARB_ID, CARB_NAME, CARB_UNIT = 1005, "Carbohydrate, by difference", "g"
FIBER_ID, FIBER_NAME, FIBER_UNIT = 1079, "Fiber, total dietary", "g"


@dataclass(frozen=True)
class NormalizedUsdaNutrition:
    kcal_100g: float | None
    carb_100g: float | None
    protein_100g: float | None
    fat_100g: float | None
    fiber_100g: float | None


def _find_amount(
    food_nutrients: list[dict], *, nutrient_id: int, name: str, unit: str
) -> float | None:
    """在 foodNutrients 数组里找 id+name+unit 三者都匹配的条目,返回其 amount。
    找不到(这个 (id,name,unit) 组合压根不在数组里)-> None。amount 必须用
    `is not None` 判断,不能用真值判断(会把合法的 0 值误判成缺失)。"""
    for entry in food_nutrients:
        nutrient = entry.get("nutrient") or {}
        if (
            nutrient.get("id") == nutrient_id
            and nutrient.get("name") == name
            and nutrient.get("unitName") == unit
        ):
            amount = entry.get("amount")
            if amount is not None:
                return float(amount)
    return None


def _find_energy_kcal(food_nutrients: list[dict]) -> float | None:
    for nutrient_id in ENERGY_KCAL_IDS:
        value = _find_amount(
            food_nutrients,
            nutrient_id=nutrient_id,
            name=ENERGY_KCAL_NAME_BY_ID[nutrient_id],
            unit=ENERGY_KCAL_UNIT,
        )
        if value is not None:
            return value
    return None


def normalize_usda_nutrition(raw_food: dict) -> NormalizedUsdaNutrition:
    """raw_food 是下载文件里数组的一个元素(已过滤掉字面 JSON null),形状固定是
    { fdcId, description, dataType, foodNutrients: [{nutrient: {id, name, unitName}, amount}] }。
    没匹配上的项目 -> None,不猜测、不用近似字段顶替。"""
    food_nutrients = raw_food.get("foodNutrients") or []
    return NormalizedUsdaNutrition(
        kcal_100g=_find_energy_kcal(food_nutrients),
        carb_100g=_find_amount(food_nutrients, nutrient_id=CARB_ID, name=CARB_NAME, unit=CARB_UNIT),
        protein_100g=_find_amount(
            food_nutrients, nutrient_id=PROTEIN_ID, name=PROTEIN_NAME, unit=PROTEIN_UNIT
        ),
        fat_100g=_find_amount(food_nutrients, nutrient_id=FAT_ID, name=FAT_NAME, unit=FAT_UNIT),
        fiber_100g=_find_amount(
            food_nutrients, nutrient_id=FIBER_ID, name=FIBER_NAME, unit=FIBER_UNIT
        ),
    )
