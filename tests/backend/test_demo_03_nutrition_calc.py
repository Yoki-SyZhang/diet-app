"""1.6 单位与营养计算引擎:克重营养换算、null 传播、营养值 0/负数/非有限值校验
(SPEC §7.3,tasks/current.md)。纯函数,不涉及 LLM/DB。
"""

import math

import pytest
from pydantic import ValidationError

from app.schemas.nutrition import NutrientPer100g, NutrientSet
from app.services.nutrition_calc import compute_nutrient_snapshot


def test_scales_all_fields_by_quantity_over_100():
    per_100g = NutrientPer100g(
        kcal_100g=200, carb_100g=20, protein_100g=10, fat_100g=5, fiber_100g=2
    )
    snapshot = compute_nutrient_snapshot(per_100g, quantity_g=150)
    assert snapshot == NutrientSet(kcal=300, carb_g=30, protein_g=15, fat_g=7.5, fiber_g=3)


def test_fractional_quantity():
    per_100g = NutrientPer100g(kcal_100g=100)
    snapshot = compute_nutrient_snapshot(per_100g, quantity_g=33.3)
    assert math.isclose(snapshot.kcal, 33.3)


def test_null_propagates_field_by_field_not_zero():
    per_100g = NutrientPer100g(kcal_100g=200, carb_100g=None, protein_100g=10, fat_100g=None)
    snapshot = compute_nutrient_snapshot(per_100g, quantity_g=100)
    assert snapshot.kcal == 200
    assert snapshot.carb_g is None
    assert snapshot.protein_g == 10
    assert snapshot.fat_g is None
    assert snapshot.fiber_g is None


def test_all_fields_null_yields_all_null_snapshot():
    snapshot = compute_nutrient_snapshot(NutrientPer100g(), quantity_g=100)
    assert snapshot == NutrientSet()


@pytest.mark.parametrize("field", ["kcal_100g", "carb_100g", "protein_100g", "fat_100g", "fiber_100g"])
def test_per_100g_rejects_negative(field):
    with pytest.raises(ValidationError):
        NutrientPer100g(**{field: -0.1})


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_per_100g_rejects_non_finite(bad_value):
    with pytest.raises(ValidationError):
        NutrientPer100g(kcal_100g=bad_value)


def test_per_100g_accepts_zero_as_legitimate_value():
    # 0 是"确定为零",不是缺失——和 None 要能区分开
    per_100g = NutrientPer100g(kcal_100g=0, protein_100g=None)
    assert per_100g.kcal_100g == 0
    assert per_100g.protein_100g is None


@pytest.mark.parametrize("field", ["kcal", "carb_g", "protein_g", "fat_g", "fiber_g"])
def test_nutrient_set_rejects_negative(field):
    with pytest.raises(ValidationError):
        NutrientSet(**{field: -1})
