import math

from pydantic import BaseModel, field_validator


def _check_nutrient(value: float | None) -> float | None:
    """缺失保持 None,不用 0 顶替;存在时必须是有限、非负数(拒绝 NaN/±inf/负数)。"""
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("营养值必须是有限数,不能是 NaN 或无穷")
    if value < 0:
        raise ValueError("营养值不能为负数")
    return value


class NutrientPer100g(BaseModel):
    """每 100g 可食部的五项营养(SPEC §4.4/§7.3)。"""

    kcal_100g: float | None = None
    carb_100g: float | None = None
    protein_100g: float | None = None
    fat_100g: float | None = None
    fiber_100g: float | None = None

    @field_validator("kcal_100g", "carb_100g", "protein_100g", "fat_100g", "fiber_100g")
    @classmethod
    def _validate_nutrients(cls, v: float | None) -> float | None:
        return _check_nutrient(v)


class NutrientSet(BaseModel):
    """按实际摄入克重计算后的营养快照,字段名对齐 `meal_entry` 落库列(SPEC §4.1)。"""

    kcal: float | None = None
    carb_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None

    @field_validator("kcal", "carb_g", "protein_g", "fat_g", "fiber_g")
    @classmethod
    def _validate_nutrients(cls, v: float | None) -> float | None:
        return _check_nutrient(v)
