"""1.5 usda_adapter:按 id+name+unit 三重匹配提取营养值,不按数组位置取值,能量多候选
按优先级取一个不相加,缺失给 None,真实 0 值保留为 0。
fixture 主要从真实下载文件截取(见各文件里的 _fixture_note),只有两条明确标注
'SYNTHETIC' 的人工构造 fixture 用于真实数据里测不到的边界情况。
"""

import json
from pathlib import Path

from app.services.usda_adapter import normalize_usda_nutrition

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "usda"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_normal_complete_record_from_real_data():
    raw = load_fixture("usda_complete_survey.json")
    result = normalize_usda_nutrition(raw)
    assert result.kcal_100g == 31.0
    assert result.protein_100g == 1.14
    assert result.fat_100g == 1.6
    assert result.carb_100g == 3.04
    assert result.fiber_100g == 0.1


def test_record_with_no_energy_entry_gives_none_not_error():
    raw = load_fixture("usda_no_energy_foundation.json")
    result = normalize_usda_nutrition(raw)
    assert result.kcal_100g is None
    assert result.protein_100g is None
    assert result.fat_100g is None
    assert result.carb_100g is None
    assert result.fiber_100g is None


def test_real_record_falls_back_to_2047_when_1008_absent():
    raw = load_fixture("usda_only_2047_foundation.json")
    result = normalize_usda_nutrition(raw)
    # 真实记录里没有 id=1008,只有 2047(61.8)和 2048(55.6);按优先级应取 2047,不取 2048
    assert result.kcal_100g == 61.8
    assert result.fat_100g == 0.212
    assert result.fiber_100g == 2.04
    assert result.protein_100g == 0.188
    assert result.carb_100g == 14.8


def test_real_zero_amount_is_kept_as_zero_not_missing():
    raw = load_fixture("usda_zero_fiber_survey.json")
    result = normalize_usda_nutrition(raw)
    assert result.fiber_100g == 0.0
    assert result.kcal_100g == 52.0


def test_synthetic_multiple_kcal_candidates_take_highest_priority_not_sum():
    raw = load_fixture("usda_synthetic_multi_kcal_ids.json")
    result = normalize_usda_nutrition(raw)
    # id=1008(100.0) 优先于 2047(999.0)/2048(888.0),且绝不相加
    assert result.kcal_100g == 100.0


def test_synthetic_wrong_unit_does_not_match_even_with_correct_id():
    raw = load_fixture("usda_synthetic_wrong_name_or_unit.json")
    result = normalize_usda_nutrition(raw)
    # id=1008 对,但 unitName 是 kJ 不是 kcal,不能被当作匹配
    assert result.kcal_100g is None
