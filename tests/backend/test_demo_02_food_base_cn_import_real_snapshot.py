"""1.4 验收:对真实本地 61 文件 OCR 快照跑 parse_food_base_cn_directory + 插入
migrated_engine 临时库,断言精确记录数(SPEC/tasks/STATUS.md 定义的验收标准)。

默认在本地快照目录不存在时跳过,不挡没有这份数据的机器/CI;设置环境变量
DIETAPP_REQUIRE_SNAPSHOTS=1 时改为 fail,保证最终验收不会被"悄悄跳过"误判成通过。
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.food_base_cn import FoodBaseCn
from app.services.food_base_cn_import import (
    insert_food_base_cn_records,
    parse_food_base_cn_directory,
)

REAL_SNAPSHOT_DIR = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "data"
    / "food_base"
    / "food_base_cn"
    / "json_data_vision_251206_Qwen2-5-VL-72B-Instruct"
)
SOURCE_COMMIT = "095034a96376d893582b412900fa8fdf792b4194"

_REQUIRE_SNAPSHOTS = os.environ.get("DIETAPP_REQUIRE_SNAPSHOTS") == "1"


def _skip_or_fail(reason: str) -> None:
    if _REQUIRE_SNAPSHOTS:
        pytest.fail(f"DIETAPP_REQUIRE_SNAPSHOTS=1 但 {reason}")
    pytest.skip(reason)


@pytest.fixture(autouse=True)
def _require_snapshot_dir():
    if not REAL_SNAPSHOT_DIR.is_dir():
        _skip_or_fail(f"本地快照目录不存在: {REAL_SNAPSHOT_DIR}")


def test_real_snapshot_parses_expected_counts():
    records, report = parse_food_base_cn_directory(REAL_SNAPSHOT_DIR, source_commit=SOURCE_COMMIT)

    assert report.files_processed == 61
    assert report.records_parsed == 1657
    assert report.fully_null_records == [("192011", "麻子籽")]
    assert len(records) == 1656

    assert report.duplicate_food_codes == {}
    assert report.edible_out_of_range == []

    assert report.dirty_value_counts["energyKCal"]["footnote_calculated"] == 18
    assert len(report.unrecognized_values) == 1


def test_real_snapshot_inserts_expected_row_count(migrated_engine):
    records, _ = parse_food_base_cn_directory(REAL_SNAPSHOT_DIR, source_commit=SOURCE_COMMIT)

    Session = sessionmaker(bind=migrated_engine)
    session = Session()
    try:
        inserted = insert_food_base_cn_records(session, records)
        session.commit()
        assert inserted == 1656

        total = len(session.scalars(select(FoodBaseCn)).all())
        assert total == 1656
    finally:
        session.close()
