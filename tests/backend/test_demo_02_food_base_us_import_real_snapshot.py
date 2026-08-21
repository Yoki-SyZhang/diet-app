"""1.5 验收:对真实下载的 Foundation(363 条)+ Survey(5432 条)USDA 快照跑
import_food_base_us_snapshot + 插入 migrated_engine 临时库,断言精确记录数
(SPEC/tasks/STATUS.md 定义的验收标准)。

默认在本地下载文件不存在时跳过,不挡没有这份数据的机器/CI;设置环境变量
DIETAPP_REQUIRE_SNAPSHOTS=1 时改为 fail,和 test_demo_02_food_base_cn_import_real_snapshot.py
同样的策略。
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.food_base_us import FoodBaseUs
from app.services.food_base_us_import import (
    import_food_base_us_snapshot,
    insert_food_base_us_records,
)

US_BASE_DIR = Path(__file__).resolve().parents[2] / "backend" / "data" / "food_base" / "food_base_us"
FOUNDATION_PATH = (
    US_BASE_DIR
    / "foundation_food_json_2026-04-30"
    / "FoodData_Central_foundation_food_json_2026-04-30.json"
)
SURVEY_PATH = (
    US_BASE_DIR / "survey_food_json_2024-10-31" / "FoodData_Central_survey_food_json_2024-10-31.json"
)

_REQUIRE_SNAPSHOTS = os.environ.get("DIETAPP_REQUIRE_SNAPSHOTS") == "1"


def _skip_or_fail(reason: str) -> None:
    if _REQUIRE_SNAPSHOTS:
        pytest.fail(f"DIETAPP_REQUIRE_SNAPSHOTS=1 但 {reason}")
    pytest.skip(reason)


@pytest.fixture(autouse=True)
def _require_snapshot_files():
    if not FOUNDATION_PATH.is_file() or not SURVEY_PATH.is_file():
        _skip_or_fail(f"本地 USDA 下载文件不存在: {FOUNDATION_PATH} / {SURVEY_PATH}")


def test_real_snapshot_parses_expected_counts():
    records, report = import_food_base_us_snapshot(FOUNDATION_PATH, SURVEY_PATH)

    assert report.files_processed == 2
    assert report.array_entries_total == 395 + 5432
    assert report.null_array_entries_skipped == 32
    assert report.records_parsed == 5795
    assert len(records) == 5795

    assert report.data_type_mismatches == []
    assert report.cross_dataset_fdc_id_collisions == []


def test_real_snapshot_inserts_expected_row_count(migrated_engine):
    records, _ = import_food_base_us_snapshot(FOUNDATION_PATH, SURVEY_PATH)

    Session = sessionmaker(bind=migrated_engine)
    session = Session()
    try:
        inserted = insert_food_base_us_records(session, records)
        session.commit()
        assert inserted == 5795

        total = len(session.scalars(select(FoodBaseUs)).all())
        assert total == 5795
    finally:
        session.close()
